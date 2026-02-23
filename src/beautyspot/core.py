# src/beautyspot/core.py

import atexit
import asyncio
import concurrent.futures
import hashlib
import logging
import functools
import inspect
import random
import threading
import warnings
import weakref
from concurrent.futures import Executor, ThreadPoolExecutor, wait
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import (
    Any,
    Callable,
    Optional,
    Union,
    Type,
    overload,
    TypeVar,
    TypeVarTuple,
    Unpack,
    ParamSpec,
    ContextManager,
    Sequence,
)

from beautyspot.maintenance import MaintenanceService
from beautyspot.limiter import LimiterProtocol
from beautyspot.storage import BlobStorageBase, StoragePolicyProtocol
from beautyspot.types import SaveErrorContext
from beautyspot.lifecycle import LifecyclePolicy, parse_retention
from beautyspot.db import TaskDBBase
from beautyspot.serializer import SerializerProtocol, TypeRegistryProtocol
from beautyspot.cachekey import KeyGen, KeyGenPolicy
from beautyspot.exceptions import (
    CacheCorruptedError,
    IncompatibleProviderError,
    ValidationError,
)
from beautyspot.hooks import HookBase
from beautyspot.types import PreExecuteContext, CacheHitContext, CacheMissContext
from beautyspot.content_types import ContentType

# ジェネリクスの定義
P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")
Ts = TypeVarTuple("Ts")

# --- キャッシュミスを表す番兵オブジェクト ---
CACHE_MISS = object()

# --- ロガー ---
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


# --- プロセス終了時のドレイン ---
_active_loops: weakref.WeakSet["_BackgroundLoop"] = weakref.WeakSet()


def _shutdown_all_loops():
    """プロセス終了時に未完了のバックグラウンドタスクを安全にドレインする安全網。"""
    for loop in list(_active_loops):
        try:
            # atexitのタイミングではプロセスが終了するため、wait=Trueで確実にデータを保存する
            # ただし無制限に待たないようタイムアウトを設定
            loop.stop(wait=True, timeout=5.0)
        except Exception as e:
            logger.error(f"Error shutting down background loop during exit: {e}")


# プロセス終了時のフックとして登録
atexit.register(_shutdown_all_loops)


class _BackgroundLoop:
    """バックグラウンドで asyncio イベントループを実行するヘルパー。

    専用スレッドで asyncio ループを動かし、保存処理を構造的に直列化する。
    ``submit()`` で投入されたコルーチンは FIFO 順に逐次実行されるため、
    ロックなしでスレッド安全性を確保できる。
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stopped = False
        self._thread.start()

        # 自身をトラッキングセットに追加
        _active_loops.add(self)

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            # メインスレッドからではなく、スレッドの終了直前に自身で確実にループを閉じる
            self._loop.close()

    def submit(self, coro) -> concurrent.futures.Future:
        """コルーチンをループに投入し、concurrent.futures.Future を返す。"""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop_gracefully_no_wait(self) -> None:
        """
        GC発生時など、メインスレッドをブロックせずに残りのタスクを完了させてから
        ループを終了するためのメソッド。
        """
        if self._stopped:
            return
        self._stopped = True

        def _drain_and_stop():
            # 自分自身（このシャットダウン処理）以外の全タスクを取得
            tasks = [
                t
                for t in asyncio.all_tasks(self._loop)
                if t is not asyncio.current_task(self._loop)
            ]

            if not tasks:
                self._loop.stop()
                return

            # タスクをキャンセルするのではなく、完了を待機する
            async def _wait_for_completion():
                await asyncio.gather(*tasks, return_exceptions=True)
                self._loop.stop()

            self._loop.create_task(_wait_for_completion())

        # スレッドセーフにシャットダウンシーケンスを投入（メインスレッドは即座にリターン）
        self._loop.call_soon_threadsafe(_drain_and_stop)

    def stop(self, wait: bool = True, timeout: float = 10.0) -> None:
        """
        ループを安全に停止する (Graceful Shutdown)。

        wait=True の場合、実行中のタスクに対してキャンセル要求 (asyncio.CancelledError)
        を送信し、それらが安全に終了するのを待機してからループを閉じます。

        Args:
            wait: True の場合、タスクのキャンセルとスレッドの終了を待機する。
            timeout: スレッド終了待機の最大時間（秒）。
        """
        if self._stopped:
            return
        self._stopped = True

        def _cancel_tasks_and_stop():
            # 現在のループで実行中の全タスクを取得（自分自身は除く）
            tasks = [
                t
                for t in asyncio.all_tasks(self._loop)
                if t is not asyncio.current_task(self._loop)
            ]

            if not tasks:
                self._loop.stop()
                return

            # 各タスクにキャンセルを要求
            for task in tasks:
                task.cancel()

            # タスクのキャンセル処理（例外の送出と捕捉）が完了するのを待機してから停止
            async def _wait_for_cancellation():
                await asyncio.gather(*tasks, return_exceptions=True)
                self._loop.stop()  # これにより run_forever() が終了し、finallyブロックへ進む

            self._loop.create_task(_wait_for_cancellation())

        # スレッドセーフにシャットダウンシーケンスを開始
        self._loop.call_soon_threadsafe(_cancel_tasks_and_stop)

        # wait=True の場合のみスレッド終了を待つ。
        # Spot.shutdown(wait=False) や GCからの呼び出しではメインスレッドをブロックしない。
        if wait:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    f"Background loop thread did not terminate within {timeout} seconds. "
                    "Some IO tasks might be stuck."
                )


class Spot:
    """
    Spot class that handles task management, serialization, and
    resource management for marked functions including caching and storage.

    .. warning::
        **リソース管理とデータロストに関する注意**
        `Spot` インスタンスは内部でバックグラウンドIO用の専用スレッドを起動します。
        関数内で一時的にインスタンスを生成して破棄するような使い方をした場合、
        ガベージコレクション(GC)時にメインスレッドのフリーズを防ぐため、未完了の保存タスクが
        **強制キャンセル（データロスト）** される可能性があります。

        安全に利用するためには、以下のいずれかのアプローチを推奨します。
        1. アプリケーションのライフサイクル全体で1つの `Spot` インスタンスを使い回す（シングルトン的利用）。
        2. コンテキストマネージャ (`with Spot(...) as spot:`) を使用し、スコープを抜ける際に確実にリソースをドレインする。
        3. 利用終了時に明示的に `spot.shutdown(wait=True)` を呼び出す。

        ※ プロセス終了時 (`atexit`) には安全網として未完了タスクのドレインを試みますが、
           GCによる破棄に対しては無力であることに注意してください。

    Args:
        name: The name of the Spot instance.
        db: The database backend for task tracking.
        serializer: The serializer for cache values.
        storage_backend: The blob storage backend.
        storage_policy: The policy to decide whether to save as blob.
        limiter: The rate limiter instance.
        executor: Optional thread pool executor for async tasks.
        io_workers: Number of workers if executor is not provided.
        default_wait: Default behavior for wait flag in saving cache.
        default_version: Default version string for cache entries.
        default_content_type: Default content type string.
        lifecycle_policy: The lifecycle retention policy.
        eviction_rate: float, optional
            The probability (0.0 to 1.0) of triggering an automatic background
            cleanup of expired cache entries and orphaned blob files after a cache miss.
            Defaults to 0.0 (disabled). Set to a small value (e.g., 0.01) for
            long-running applications to prevent storage bloat without blocking the main thread.
        on_background_error: バックグラウンドでのキャッシュ保存 (wait=False) 時に
            例外が発生した際に呼び出されるコールバック関数。
            メインスレッドの処理を阻害することなく、保存失敗のログ収集や
            監視ツールへの通知を行うために使用します。
            コールバックには、発生した `Exception` と詳細な `SaveErrorContext` が渡されます。
            この関数内で発生した例外は安全にキャッチされ、アプリケーションはクラッシュしません。
    """

    def __init__(
        self,
        name: str,
        # 必須の依存オブジェクト (DI)
        db: TaskDBBase,
        serializer: SerializerProtocol,
        storage_backend: BlobStorageBase,
        storage_policy: StoragePolicyProtocol,
        limiter: LimiterProtocol,
        # オプション設定
        executor: Optional[Executor] = None,
        io_workers: int = 4,
        default_wait: bool = True,
        # デフォルト動作設定
        default_version: Optional[str] = None,
        default_content_type: Optional[str | ContentType] = None,
        lifecycle_policy: Optional[LifecyclePolicy] = None,
        eviction_rate: float = 0.0,
        on_background_error: Optional[
            Callable[[Exception, SaveErrorContext], None]
        ] = None,
    ) -> None:
        self.name = name
        if not (0.0 <= eviction_rate <= 1.0):
            raise ValueError("eviction_rate must be between 0.0 and 1.0")
        self.eviction_rate = eviction_rate

        # --- 依存オブジェクトの注入 ---
        self.db = db
        self.serializer = serializer
        self.storage_backend = storage_backend
        self.storage_policy = storage_policy
        self.limiter = limiter

        # --- オプション設定の適用 ---
        self.default_version = default_version
        self.default_content_type = default_content_type
        self.default_wait = default_wait
        self.lifecycle_policy = lifecycle_policy or LifecyclePolicy.default()
        self.on_background_error = on_background_error

        # --- DBの初期化 ---
        self.db.init_schema()

        # --- バックグラウンド IO 管理 ---
        if executor is not None:
            warnings.warn(
                "The 'executor' parameter is deprecated. "
                "beautyspot now uses an internal asyncio event loop for background IO.",
                DeprecationWarning,
                stacklevel=2,
            )
            # レガシーパス: 従来の ThreadPoolExecutor 動作
            self._bg_loop: _BackgroundLoop | None = None
            self._executor: Executor | None = executor
            self._own_executor = False
            self._finalizer = None
        else:
            # 新パス: 専用 asyncio ループ (wait=False 保存用) +
            # スレッドプール (async パスの run_in_executor 用)
            self._bg_loop = _BackgroundLoop()
            self._executor = ThreadPoolExecutor(max_workers=io_workers)
            self._own_executor = True
            # GC時の安全なシャットダウン
            self._finalizer = weakref.finalize(
                self, Spot._shutdown_resources, self._bg_loop, self._executor
            )

        # 実行中のタスクを管理するセット (ロックで保護)
        self._active_futures: set = set()
        self._futures_lock = threading.Lock()

    def __enter__(self) -> "Spot":
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        コンテキストを抜ける際の処理。
        バックグラウンドループは停止させず、現在実行中のタスクの完了だけを待つ。
        これにより、同じSpotインスタンスを別の with ブロックで再利用可能にする。
        """
        self._drain_futures()

    def _track_future(self, future: Any):
        """Futureを追跡セットに加え、完了したら削除する"""
        with self._futures_lock:
            self._active_futures.add(future)

        def _on_done(f):
            with self._futures_lock:
                self._active_futures.discard(f)

        future.add_done_callback(_on_done)

    @property
    def maintenance(self) -> MaintenanceService:
        """
        MaintenanceService を遅延評価で生成・取得します。
        Spot初期化時の循環参照や不要なインポートを防ぎます。
        """
        if getattr(self, "_maintenance_service", None) is None:
            self._maintenance_service = MaintenanceService(
                db=self.db,
                storage=self.storage_backend,
                serializer=self.serializer,
            )
        return self._maintenance_service

    @staticmethod
    def _setup_workspace(workspace_dir: Path):
        """Ensure the workspace directory and .gitignore exist."""
        workspace_dir.mkdir(parents=True, exist_ok=True)

        gitignore_path = workspace_dir / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text("*\n")

    @staticmethod
    def _shutdown_resources(bg_loop: _BackgroundLoop, executor: Executor) -> None:
        """GC finalizer 用: リソースを即座に解放する (wait=False)。"""
        bg_loop.stop_gracefully_no_wait()
        executor.shutdown(wait=False)

    def shutdown(self, wait: bool = True):
        """バックグラウンド IO を停止する。

        wait=True の場合、保留中のすべての Future を先にドレインしてから停止する。
        """
        if not self._own_executor:
            return
        if self._finalizer is not None and self._finalizer.alive:
            self._finalizer.detach()
        if wait:
            self._drain_futures()
        if self._bg_loop is not None:
            self._bg_loop.stop(wait=wait)
        if self._executor is not None:
            self._executor.shutdown(wait=wait)

    _MAX_DRAIN_ITERATIONS = 10

    def _drain_futures(self) -> None:
        """保留中のすべての Future が完了するまで待機するドレインループ。"""
        for i in range(self._MAX_DRAIN_ITERATIONS):
            with self._futures_lock:
                snapshot = list(self._active_futures)
            if not snapshot:
                break
            wait(snapshot)
        else:
            with self._futures_lock:
                remaining = len(self._active_futures)
            if remaining:
                logger.warning(
                    f"Drain loop reached max iterations ({self._MAX_DRAIN_ITERATIONS}) "
                    f"with {remaining} futures still pending."
                )

    def _trigger_auto_eviction(self) -> None:
        """確率に応じてバックグラウンドで自動クリーンアップ(エビクション)をエンキューする"""
        if self.eviction_rate <= 0.0:
            return

        if random.random() < self.eviction_rate:
            logger.debug(f"Triggering auto-eviction (rate: {self.eviction_rate})")

            maintenance = self.maintenance

            if self._bg_loop is not None:
                # _bg_loop.submit はコルーチンを受け取るため、同期関数をラップする
                async def _run_clean():
                    loop = asyncio.get_running_loop()
                    # デフォルトエグゼキュータ（別スレッド）でI/Oブロッキングな掃除処理を実行
                    await loop.run_in_executor(None, maintenance.clean_garbage)

                future = self._bg_loop.submit(_run_clean())
                self._track_future(future)

            elif self._executor is not None:
                # レガシーパス用
                future = self._executor.submit(maintenance.clean_garbage)
                self._track_future(future)

    def _resolve_key_fn(
        self,
        func: Callable,
        keygen: Optional[Union[Callable, KeyGenPolicy]] = None,
        input_key_fn: Optional[Union[Callable, KeyGenPolicy]] = None,
    ) -> Optional[Callable]:
        if keygen is not None and input_key_fn is not None:
            raise IncompatibleProviderError(
                "Cannot specify both 'keygen' and 'input_key_fn'. Please use 'keygen'."
            )

        target = keygen

        if input_key_fn is not None:
            warnings.warn(
                "The 'input_key_fn' argument is deprecated and will be removed in v3.0. "
                "Please use 'keygen' instead.",
                DeprecationWarning,
                stacklevel=3,
            )
            target = input_key_fn

        if isinstance(target, KeyGenPolicy):
            return target.bind(func)

        return target

    def register(
        self,
        code: int,
        encoder: Callable[[T], Any],
        decoder: Optional[Callable[[Any], T]] = None,
        decoder_factory: Optional[Callable[[Type[T]], Callable[[Any], T]]] = None,
    ) -> Callable[[Type[T]], Type[T]]:
        if decoder is None and decoder_factory is None:
            raise IncompatibleProviderError(
                "Must provide either `decoder` or `decoder_factory`."
            )

        def decorator(cls: Type) -> Type:
            actual_decoder = decoder
            if decoder_factory:
                actual_decoder = decoder_factory(cls)

            if actual_decoder is None:
                raise ValueError("Decoder resolution failed.")

            self.register_type(cls, code, encoder, actual_decoder)
            return cls

        return decorator

    def register_type(
        self,
        type_class: Type[T],
        code: int,
        encoder: Callable[[T], Any],
        decoder: Callable[[Any], T],
    ):
        if isinstance(self.serializer, TypeRegistryProtocol):
            self.serializer.register(type_class, code, encoder, decoder)
        else:
            raise NotImplementedError(
                f"The current serializer '{type(self.serializer).__name__}' does not support type registration.\n"
                "The `@spot.register` decorator is only compatible with the default MsgpackSerializer."
            )

    # --- ヘルパーメソッド: 有効期限の計算 ---
    def _calculate_expires_at(
        self, func_name: str, local_retention: Union[str, timedelta, None]
    ) -> Optional[datetime]:

        # 1. ローカル指定 (優先度: 高)
        retention = parse_retention(local_retention)

        # 2. ポリシー指定 (優先度: 低)
        if retention is None:
            retention = self.lifecycle_policy.resolve(func_name)

        if retention is None:
            return None  # 無期限

        return datetime.now(timezone.utc) + retention

    # --- Hook ディスパッチヘルパー ---
    @staticmethod
    def _dispatch_hooks(
        hooks: Optional[Sequence[HookBase]],
        method_name: str,
        context: Any,
    ) -> None:
        """フックのコールバックを安全に呼び出す。例外はログに記録し、呼び出し元には伝播しない。"""
        if not hooks:
            return
        for hook in hooks:
            try:
                getattr(hook, method_name)(context)
            except Exception as e:
                logger.error(
                    f"Error in hook '{type(hook).__name__}.{method_name}': {e}",
                    exc_info=True,
                )

    # --- Core Logic (Sync) ---
    def _resolve_settings(
        self,
        save_blob: bool | None,
        version: str | None,
        content_type: str | ContentType | None,
        wait: bool | None,
    ) -> tuple[bool | None, str | None, str | None, bool]:
        # [CHANGED] save_blob が None の場合、ここで False に解決せず None のまま通す。
        # これにより _save_result_sync で policy.should_save_as_blob() が呼ばれるようになる。
        final_save_blob = save_blob

        final_version = version if version is not None else self.default_version
        final_content_type = (
            content_type if content_type is not None else self.default_content_type
        )
        final_wait = wait if wait is not None else self.default_wait

        return final_save_blob, final_version, final_content_type, final_wait

    def _make_cache_key(
        self,
        func_name: str,
        args: tuple,
        kwargs: dict,
        resolved_key_fn: Optional[Callable],
        version: str | None,
    ) -> tuple[str, str]:
        iid = (
            resolved_key_fn(*args, **kwargs)
            if resolved_key_fn
            else KeyGen._default(args, kwargs)
        )

        key_source = f"{func_name}:{iid}"
        if version:
            key_source += f":{version}"

        ck = hashlib.sha256(key_source.encode()).hexdigest()
        return iid, ck

    def _execute_sync(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        save_blob: bool | None,
        effective_key_fn: Optional[Callable],
        version: str | None,
        content_type: Optional[str | ContentType],
        serializer: Optional[SerializerProtocol],
        retention: Union[str, timedelta, None],
        wait: bool | None,
        hooks: Optional[Sequence[HookBase]] = None,
    ) -> Any:
        # Resolve Defaults (wait もここで解決)
        s_blob, s_ver, s_ct, s_wait = self._resolve_settings(
            save_blob, version, content_type, wait
        )

        iid, ck = self._make_cache_key(
            func.__name__, args, kwargs, effective_key_fn, s_ver
        )

        # kwargs をコピーしてフックからの変更を防止
        hook_kwargs = dict(kwargs) if hooks else kwargs

        # === 1. フック: pre_execute ===
        self._dispatch_hooks(
            hooks,
            "pre_execute",
            PreExecuteContext(
                func_name=func.__name__,
                input_id=str(iid),
                cache_key=ck,
                args=args,
                kwargs=hook_kwargs,
            ),
        )

        # === 2. Check Cache ===
        cached = self._check_cache_sync(ck, serializer)
        if cached is not CACHE_MISS:
            self._dispatch_hooks(
                hooks,
                "on_cache_hit",
                CacheHitContext(
                    func_name=func.__name__,
                    input_id=str(iid),
                    cache_key=ck,
                    args=args,
                    kwargs=hook_kwargs,
                    result=cached,
                    version=s_ver,
                ),
            )
            return cached

        # === 3. Execute ===
        res = func(*args, **kwargs)

        # === 4. フック: on_cache_miss ===
        self._dispatch_hooks(
            hooks,
            "on_cache_miss",
            CacheMissContext(
                func_name=func.__name__,
                input_id=str(iid),
                cache_key=ck,
                args=args,
                kwargs=hook_kwargs,
                result=res,
                version=s_ver,
            ),
        )

        # === 5. Calculate Expiration & Save ===
        expires_at = self._calculate_expires_at(func.__name__, retention)
        save_kwargs = {
            "cache_key": ck,
            "func_name": func.__name__,
            "input_id": str(iid),
            "version": s_ver,
            "result": res,
            "content_type": s_ct,
            "save_blob": s_blob,
            "serializer": serializer,
            "expires_at": expires_at,
        }

        if s_wait:
            self._save_result_sync(**save_kwargs)
        else:
            self._submit_background_save(**save_kwargs)

        # [ADD] 保存後に自動クリーンアップのトリガー判定
        self._trigger_auto_eviction()

        return res

    async def _execute_async(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        save_blob: bool | None,
        effective_key_fn: Optional[Callable],
        version: str | None,
        content_type: Optional[str | ContentType],
        serializer: Optional[SerializerProtocol],
        retention: Union[str, timedelta, None],
        wait: bool | None,
        hooks: Optional[Sequence[HookBase]] = None,
    ) -> Any:
        # Resolve Defaults
        s_blob, s_ver, s_ct, s_wait = self._resolve_settings(
            save_blob, version, content_type, wait
        )

        iid, ck = self._make_cache_key(
            func.__name__, args, kwargs, effective_key_fn, s_ver
        )
        loop = asyncio.get_running_loop()

        # kwargs をコピーしてフックからの変更を防止
        hook_kwargs = dict(kwargs) if hooks else kwargs

        # === 1. フック: pre_execute ===
        self._dispatch_hooks(
            hooks,
            "pre_execute",
            PreExecuteContext(
                func_name=func.__name__,
                input_id=str(iid),
                cache_key=ck,
                args=args,
                kwargs=hook_kwargs,
            ),
        )

        # === 2. Check Cache (Offload IO) ===
        cached = await loop.run_in_executor(
            self._executor, self._check_cache_sync, ck, serializer
        )
        if cached is not CACHE_MISS:
            self._dispatch_hooks(
                hooks,
                "on_cache_hit",
                CacheHitContext(
                    func_name=func.__name__,
                    input_id=str(iid),
                    cache_key=ck,
                    args=args,
                    kwargs=hook_kwargs,
                    result=cached,
                    version=s_ver,
                ),
            )
            return cached

        # === 3. Execute (async) ===
        res = await func(*args, **kwargs)

        # === 4. フック: on_cache_miss ===
        self._dispatch_hooks(
            hooks,
            "on_cache_miss",
            CacheMissContext(
                func_name=func.__name__,
                input_id=str(iid),
                cache_key=ck,
                args=args,
                kwargs=hook_kwargs,
                result=res,
                version=s_ver,
            ),
        )

        # === 5. Calculate Expiration & Save ===
        expires_at = self._calculate_expires_at(func.__name__, retention)

        save_kwargs = {
            "cache_key": ck,
            "func_name": func.__name__,
            "input_id": str(iid),
            "version": s_ver,
            "result": res,
            "content_type": s_ct,
            "save_blob": s_blob,
            "serializer": serializer,
            "expires_at": expires_at,
        }

        if s_wait:
            await loop.run_in_executor(
                self._executor,
                functools.partial(self._save_result_sync, **save_kwargs),
            )
        else:
            self._submit_background_save(**save_kwargs)

        # [ADD] 保存後に自動クリーンアップのトリガー判定
        self._trigger_auto_eviction()

        return res

    def _check_cache_sync(
        self, cache_key: str, serializer: Optional[SerializerProtocol] = None
    ) -> Any:
        use_serializer = serializer or self.serializer

        entry = self.db.get(cache_key)

        if entry:
            r_type = entry["result_type"]
            r_val = entry["result_value"]
            r_data = entry.get("result_data")

            # Case 1: Native SQLite BLOB
            if r_type == "DIRECT_BLOB":
                if r_data is None:
                    return CACHE_MISS
                try:
                    return use_serializer.loads(r_data)
                except Exception as e:
                    logger.error(
                        f"Failed to deserialize DIRECT_BLOB for `{cache_key}`: {e}"
                    )
                    return CACHE_MISS

            # Case 2: External Blob
            elif r_type == "FILE":
                if r_val is None:
                    logger.warning(
                        f"Data corruption: 'FILE' type record has no path for key `{cache_key}`"
                    )
                    return CACHE_MISS
                try:
                    data_bytes = self.storage_backend.load(r_val)
                    return use_serializer.loads(data_bytes)
                except CacheCorruptedError as e:
                    logger.debug(
                        f"Cache corrupted or lost for {cache_key}, falling back to CACHE_MISS: {e}"
                    )
                    return CACHE_MISS

        return CACHE_MISS

    # --- バックグラウンド保存の投入 ---
    def _submit_background_save(self, **save_kwargs) -> None:
        """wait=False 時にバックグラウンドへ保存処理を投入する。"""
        if self._bg_loop is not None:
            coro = self._save_result_async(**save_kwargs)
            try:
                future = self._bg_loop.submit(coro)
            except RuntimeError:
                coro.close()  # コルーチンを安全にクリーンアップ
                raise
        else:
            assert self._executor is not None
            future = self._executor.submit(self._save_result_safe, **save_kwargs)
        self._track_future(future)

    async def _save_result_async(self, /, **kwargs) -> None:
        """バックグラウンドループで実行される保存コルーチン。"""
        self._save_result_safe(**kwargs)

    # --- 安全なバックグラウンド実行用ラッパー ---
    def _save_result_safe(self, /, **kwargs):
        """
        Wrapper for _save_result_sync to handle exceptions in background threads.
        """
        try:
            self._save_result_sync(**kwargs)
        except Exception as e:
            func_name = kwargs.get("func_name", "unknown")
            logger.error(
                f"Background save failed for task '{func_name}': {e}", exc_info=True
            )
            # [追加] コールバックが設定されていれば呼び出す
            if self.on_background_error:
                try:
                    # ユーザーのコールバック内でのエラーがスレッドをクラッシュさせないように保護
                    # kwargs から SaveErrorContext を構築して渡す
                    # serializer 等の内部オブジェクトは除外してユーザーに必要なものだけを渡す
                    context = SaveErrorContext(
                        func_name=func_name,
                        cache_key=kwargs.get("cache_key", ""),
                        input_id=kwargs.get("input_id", ""),
                        version=kwargs.get("version"),
                        content_type=kwargs.get("content_type"),
                        save_blob=kwargs.get("save_blob"),
                        expires_at=kwargs.get("expires_at"),
                        result=kwargs.get("result"),
                    )
                    self.on_background_error(e, context)
                except Exception as cb_err:
                    logger.error(
                        f"Error occurred within the 'on_background_error' callback: {cb_err}",
                        exc_info=True,
                    )

    def _save_result_sync(
        self,
        cache_key: str,
        func_name: str,
        input_id: str,
        version: str | None,
        result: Any,
        content_type: str | ContentType | None,
        save_blob: bool | None,
        serializer: Optional[SerializerProtocol] = None,
        expires_at: Optional[datetime] = None,
    ):
        use_serializer = serializer or self.serializer

        data_bytes = use_serializer.dumps(result)

        # 1. 明示的な指定(True/False)があればそれに従う
        # 2. なければ(Noneであれば)ポリシーに問い合わせる
        if save_blob is not None:
            should_use_blob = save_blob
        else:
            should_use_blob = self.storage_policy.should_save_as_blob(data_bytes)

        r_val = None
        r_blob = None
        r_type = "DIRECT_BLOB"

        if should_use_blob:
            r_val = self.storage_backend.save(cache_key, data_bytes)
            r_type = "FILE"
        else:
            r_blob = data_bytes
            r_type = "DIRECT_BLOB"

        self.db.save(
            cache_key=cache_key,
            func_name=func_name,
            input_id=input_id,
            version=version,
            result_type=r_type,
            content_type=content_type,
            result_value=r_val,
            result_data=r_blob,
            expires_at=expires_at,
        )

    def consume(self, cost: Union[int, Callable] = 1):
        def decorator(func):
            is_async = inspect.iscoroutinefunction(func)

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                c = cost(*args, **kwargs) if callable(cost) else cost
                self.limiter.consume(c)
                return func(*args, **kwargs)

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                c = cost(*args, **kwargs) if callable(cost) else cost
                await self.limiter.consume_async(c)
                return await func(*args, **kwargs)

            return async_wrapper if is_async else sync_wrapper

        return decorator

    @overload
    def mark(self, _func: Callable[P, R]) -> Callable[P, R]: ...

    @overload
    def mark(
        self,
        *,
        save_blob: Optional[bool] = None,
        keygen: Optional[Union[Callable, KeyGenPolicy]] = None,
        input_key_fn: Optional[Union[Callable, KeyGenPolicy]] = None,
        version: str | None = None,
        content_type: Optional[str | ContentType] = None,
        serializer: Optional[SerializerProtocol] = None,
        wait: Optional[bool] = None,
        retention: Union[str, timedelta, None] = None,
        hooks: Optional[Sequence[HookBase]] = None,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]: ...

    def mark(
        self,
        _func: Optional[Callable] = None,
        *,
        save_blob: Optional[bool] = None,
        keygen: Optional[Union[Callable, KeyGenPolicy]] = None,
        input_key_fn: Optional[Union[Callable, KeyGenPolicy]] = None,
        version: str | None = None,
        content_type: Optional[str | ContentType] = None,
        serializer: Optional[SerializerProtocol] = None,
        wait: Optional[bool] = None,
        retention: Union[str, timedelta, None] = None,
        hooks: Optional[Sequence[HookBase]] = None,
    ) -> Any:
        """
        Decorator to mark a function for caching and persistence.
        All logic is delegated to _execute_sync or _execute_async.
        """

        def decorator(func):
            # --- 1. Eager Validation (定義時チェック) ---
            # ここで _resolve_key_fn を呼ぶことで、不正な引数の組み合わせや
            # 非推奨パラメータの使用に対して、定義時に即座にエラー/警告を出します。
            # これにより既存のテスト (test_params_migration.py) が通るようになります。
            effective_key_fn = self._resolve_key_fn(func, keygen, input_key_fn)

            is_async = inspect.iscoroutinefunction(func)

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                return self._execute_sync(
                    func=func,
                    args=args,
                    kwargs=kwargs,
                    save_blob=save_blob,
                    effective_key_fn=effective_key_fn,
                    version=version,
                    content_type=content_type,
                    serializer=serializer,
                    wait=wait,  # None のまま渡す
                    retention=retention,
                    hooks=hooks,
                )

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await self._execute_async(
                    func=func,
                    args=args,
                    kwargs=kwargs,
                    save_blob=save_blob,
                    effective_key_fn=effective_key_fn,
                    version=version,
                    content_type=content_type,
                    serializer=serializer,
                    wait=wait,  # None のまま渡す
                    retention=retention,
                    hooks=hooks,
                )

            return async_wrapper if is_async else sync_wrapper

        if _func is not None and callable(_func):
            return decorator(_func)
        return decorator

    @overload
    def cached_run(
        self,
        func: T,
        /,
        *,
        save_blob: Optional[bool] = None,
        keygen: Optional[Union[Callable, KeyGenPolicy]] = None,
        input_key_fn: Optional[Union[Callable, KeyGenPolicy]] = None,
        version: str | None = None,
        content_type: Optional[str | ContentType] = None,
        serializer: Optional[SerializerProtocol] = None,
        wait: Optional[bool] = None,
        retention: Union[str, timedelta, None] = None,
        hooks: Optional[Sequence[HookBase]] = None,
    ) -> ContextManager[T]: ...

    @overload
    def cached_run(
        self,
        *funcs: Unpack[Ts],
        save_blob: Optional[bool] = None,
        keygen: Optional[Union[Callable, KeyGenPolicy]] = None,
        input_key_fn: Optional[Union[Callable, KeyGenPolicy]] = None,
        version: str | None = None,
        content_type: Optional[str | ContentType] = None,
        serializer: Optional[SerializerProtocol] = None,
        wait: Optional[bool] = None,
        retention: Union[str, timedelta, None] = None,
        hooks: Optional[Sequence[HookBase]] = None,
    ) -> ContextManager[tuple[Unpack[Ts]]]: ...

    @contextmanager
    def cached_run(
        self,
        *funcs: Any,
        save_blob: Optional[bool] = None,
        keygen: Optional[Union[Callable, KeyGenPolicy]] = None,
        input_key_fn: Optional[Union[Callable, KeyGenPolicy]] = None,
        version: str | None = None,
        content_type: Optional[str | ContentType] = None,
        serializer: Optional[SerializerProtocol] = None,
        wait: Optional[bool] = None,
        retention: Union[str, timedelta, None] = None,
        hooks: Optional[Sequence[HookBase]] = None,
    ):
        if not funcs:
            raise ValidationError(
                "At least one function must be provided to cached_run."
            )

        for f in funcs:
            if not callable(f):
                raise ValidationError(
                    f"All arguments to cached_run must be callable. Got: {type(f)}"
                )

        def make_cached(func):
            cache_decorator = self.mark(
                save_blob=save_blob,
                keygen=keygen,
                input_key_fn=input_key_fn,
                version=version,
                content_type=content_type,
                serializer=serializer,
                wait=wait,
                retention=retention,
                hooks=hooks,
            )
            return cache_decorator(func)

        wrappers = [make_cached(f) for f in funcs]
        if len(wrappers) == 1:
            yield wrappers[0]
        else:
            yield tuple(wrappers)
