# src/beautyspot/core.py

import atexit
import asyncio
import hashlib
import logging
import functools
import inspect
import random
import threading
import warnings
import weakref
import time
from concurrent.futures import Executor, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import (
    Any,
    Coroutine,
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


class _BackgroundLoop:
    """
    バックグラウンドで非同期IOタスクを処理するイベントループ。
    明示的なタスク追跡とスレッドロックにより、シャットダウン時の競合状態を完全に排除します。
    """

    def __init__(self, drain_timeout: float = 5.0):
        self._drain_timeout = drain_timeout
        self._loop = asyncio.new_event_loop()

        self._lock = threading.Lock()
        self._is_shutting_down = False
        self._active_tasks = 0  # 実行中（またはスケジュール待ち）のタスク数

        # daemon=True により、プロセス終了時の Python の無限ハングアップを防ぐ
        self._thread = threading.Thread(
            target=self._run_event_loop, daemon=True, name="BeautySpot-BGLoop"
        )
        self._thread.start()

        # インスタンス自身が atexit を管理するため、グローバルな _active_loops 管理は不要
        atexit.register(self._shutdown)

    def _run_event_loop(self):
        """専用スレッド内でイベントループを実行する"""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    async def _task_wrapper(self, coro: Coroutine) -> Any:
        """タスクの完了を確実にフックし、必要ならループを停止するラッパー"""
        try:
            return await coro
        finally:
            with self._lock:
                self._active_tasks -= 1
                # シャットダウン中で、かつ最後のタスクが終わった瞬間ならループを止める
                if self._is_shutting_down and self._active_tasks == 0:
                    self._loop.call_soon_threadsafe(self._loop.stop)

    def submit(self, coro: Coroutine) -> Optional[Future[Any]]:
        """スレッドセーフにタスクを投入する"""
        with self._lock:
            if self._is_shutting_down:
                logger.debug("Background loop is shutting down. Task rejected.")
                try:
                    coro.close()
                except Exception:
                    # Best-effort cleanup; avoid raising during rejection.
                    pass
                return None

            # ロック内でカウンタを増やすことで、確実にインフライトとして追跡される
            self._active_tasks += 1

        try:
            return asyncio.run_coroutine_threadsafe(
                self._task_wrapper(coro), self._loop
            )
        except Exception:
            # 万が一スケジュールに失敗した場合はカウンタを戻す
            with self._lock:
                self._active_tasks -= 1
                # シャットダウン中かつ最後のタスクだった場合、ループ停止を通知する
                if self._is_shutting_down and self._active_tasks == 0:
                    self._loop.call_soon_threadsafe(self._loop.stop)
            raise

    def stop(self, wait: bool = True):
        """
        ループに対して新規タスクの受付停止を通知し、シャットダウンシーケンスを開始する。
        Spot.shutdown() や GCの _shutdown_resources() から呼び出される統一されたAPI。
        """
        with self._lock:
            # 既にシャットダウン中であれば二重実行を避ける
            if self._is_shutting_down:
                return
            self._is_shutting_down = True

            # 現在アクティブなタスクがゼロなら、即座にループ停止をスケジュール
            if self._active_tasks == 0:
                self._loop.call_soon_threadsafe(self._loop.stop)

        if wait:
            # アクティブなタスクが残っている場合は、最後の _task_wrapper が stop() を呼ぶ
            # タイムアウト付きでスレッドの終了（＝ループの停止）を待つ
            self._thread.join(timeout=self._drain_timeout)

            if self._thread.is_alive():
                logger.warning(
                    f"BeautySpot background loop did not finish within {self._drain_timeout}s. "
                    "Pending IO tasks have been abruptly terminated."
                )

    def _shutdown(self):
        """
        [atexit フック]
        プロセス終了時に呼ばれる安全網。タイムアウト付きの待機を実行する。
        """
        self.stop(wait=True)


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
        on_background_error: キャッシュ保存 (wait=False/True) 時に
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
        drain_timeout: float = 5.0,
        drain_poll_interval: float = 0.5,
        on_background_error: Optional[
            Callable[[Exception, SaveErrorContext], None]
        ] = None,
    ) -> None:
        self.name = name
        if not (0.0 <= eviction_rate <= 1.0):
            raise ValueError("eviction_rate must be between 0.0 and 1.0")
        self.eviction_rate = eviction_rate
        if drain_timeout <= 0:
            raise ValueError("drain_timeout must be positive")
        if drain_poll_interval <= 0:
            raise ValueError("drain_poll_interval must be positive")
        self._drain_timeout = drain_timeout
        self._drain_poll_interval = drain_poll_interval

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
        self._io_workers = io_workers
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
            self._finalizer: weakref.finalize | None = None
        else:
            # 新パス: 遅延初期化 (初回 wait=False 使用時に _ensure_bg_resources() で生成)
            self._bg_loop = None
            self._executor = None
            self._own_executor = True
            self._finalizer = None

        self._bg_init_lock = threading.Lock()
        self._shutdown_called = False

        # 実行中のタスクを管理するセット (ロックで保護)
        self._active_futures: set = set()
        self._futures_lock = threading.Lock()

        # MaintenanceService の遅延初期化用
        self._maintenance_service: MaintenanceService | None = None
        self._maintenance_lock = threading.Lock()
        self._eviction_lock = threading.Lock()

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
        if future is None:
            return
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
        if self._maintenance_service is None:
            with self._maintenance_lock:
                if self._maintenance_service is None:
                    self._maintenance_service = MaintenanceService(
                        db=self.db,
                        storage=self.storage_backend,
                        serializer=self.serializer,
                    )
        assert self._maintenance_service is not None
        return self._maintenance_service

    def _ensure_bg_resources(self) -> tuple[_BackgroundLoop, Executor]:
        """バックグラウンドリソースを遅延初期化し、(bg_loop, executor) を返す。

        初回の wait=False 保存や async パスで呼ばれた時点でリソースを生成する。
        default_wait=True で wait=False を一度も使わないユーザーには
        スレッドやイベントループを一切作らない。

        Raises:
            RuntimeError: shutdown() が既に呼ばれている場合。
        """
        if self._bg_loop is not None and self._executor is not None:
            return self._bg_loop, self._executor

        with self._bg_init_lock:
            if self._shutdown_called:
                raise RuntimeError(
                    "Cannot submit background tasks after shutdown() has been called."
                )
            # Double-checked locking: 各リソースを独立チェックし既存のものは上書きしない
            if self._bg_loop is None or self._executor is None:
                if self._bg_loop is None:
                    self._bg_loop = _BackgroundLoop(drain_timeout=self._drain_timeout)
                if self._executor is None:
                    self._executor = ThreadPoolExecutor(max_workers=self._io_workers)
                if self._own_executor and self._finalizer is None:
                    self._finalizer = weakref.finalize(
                        self, Spot._shutdown_resources, self._bg_loop, self._executor
                    )
            return self._bg_loop, self._executor

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
        bg_loop.stop(wait=False)
        executor.shutdown(wait=False)

    def shutdown(self, wait: bool = True):
        """バックグラウンド IO を停止する。

        wait=True の場合、保留中のすべての Future を先にドレインしてから停止する。
        _bg_loop は常に内部生成なので停止する。executor は自身が所有する場合のみシャットダウン。
        """
        self._shutdown_called = True
        if self._finalizer is not None and self._finalizer.alive:
            self._finalizer.detach()
        if wait:
            self._drain_futures()
        # _bg_loop は常に内部生成なので停止する
        if self._bg_loop is not None:
            self._bg_loop.stop(wait=wait)
        # executor は自身が所有する場合のみシャットダウン
        if self._own_executor and self._executor is not None:
            self._executor.shutdown(wait=wait)
        try:
            self.db.shutdown(wait=wait)
        except Exception as e:
            logger.error(f"Failed to shut down DB cleanly (ignored): {e}", exc_info=True)

    def _drain_futures(self) -> None:
        """保留中のすべての Future が完了するまで待機するドレインループ。"""
        deadline = time.monotonic() + self._drain_timeout
        while True:
            with self._futures_lock:
                snapshot = list(self._active_futures)
            if not snapshot:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            wait_timeout = min(self._drain_poll_interval, remaining)
            _, not_done = wait(snapshot, timeout=wait_timeout)
            if not not_done:
                return

        with self._futures_lock:
            remaining_count = len(self._active_futures)
        if remaining_count:
            logger.warning(
                f"Drain timeout ({self._drain_timeout}s) reached with "
                f"{remaining_count} futures still pending."
            )

    @staticmethod
    def _get_func_identifier(func: Callable) -> str:
        """Derive a fully-qualified identifier for cache key namespacing."""
        module = getattr(func, "__module__", None) or func.__class__.__module__
        qualname = getattr(func, "__qualname__", None) or func.__class__.__qualname__
        return f"{module}.{qualname}"


    def _trigger_auto_eviction(self) -> None:
        """確率に応じてバックグラウンドで自動クリーンアップをエンキューする"""
        if self.eviction_rate <= 0.0:
            return

        if random.random() < self.eviction_rate:
            # 非ブロッキングでロック取得を試みる。取得できなければ既に実行中なのでスキップ。
            if not self._eviction_lock.acquire(blocking=False):
                return

            logger.debug(f"Triggering auto-eviction (rate: {self.eviction_rate})")
            maintenance = self.maintenance

            # ロックを確実に解放するためのラッパー
            def _run_clean_safe():
                try:
                    maintenance.clean_garbage()
                finally:
                    self._eviction_lock.release()

            try:
                if self._own_executor:
                    bg_loop, executor = self._ensure_bg_resources()

                    async def _run_clean_coro():
                        loop = asyncio.get_running_loop()
                        # ラッパーを介して実行
                        await loop.run_in_executor(executor, _run_clean_safe)

                    coro = _run_clean_coro()
                    future = bg_loop.submit(coro)
                    if future is None:
                        coro.close()
                        self._eviction_lock.release()
                        return
                    self._track_future(future)

                elif self._executor is not None:
                    # レガシーパス用
                    future = self._executor.submit(_run_clean_safe)
                    self._track_future(future)
            except Exception:
                # スケジュール自体に失敗した場合は、ロックを戻しておく
                self._eviction_lock.release()
                raise

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
        self,
        func_identifier: str,
        func_name: str,
        local_retention: Union[str, timedelta, None],
    ) -> Optional[datetime]:

        # 1. ローカル指定 (優先度: 高)
        retention = parse_retention(local_retention)

        # 2. ポリシー指定 (優先度: 低)
        if retention is None:
            retention = self.lifecycle_policy.resolve_with_fallback(
                func_identifier, func_name
            )

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
        func_identifier: str,
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

        key_source = f"{func_identifier}:{iid}"
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

        func_identifier = self._get_func_identifier(func)
        iid, ck = self._make_cache_key(
            func_identifier, args, kwargs, effective_key_fn, s_ver
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
        expires_at = self._calculate_expires_at(func_identifier, func.__name__, retention)
        save_kwargs = {
            "cache_key": ck,
            "func_name": func.__name__,
            "func_identifier": func_identifier,
            "input_id": str(iid),
            "version": s_ver,
            "result": res,
            "content_type": s_ct,
            "save_blob": s_blob,
            "serializer": serializer,
            "expires_at": expires_at,
        }

        if s_wait:
            try:
                self._save_result_sync(**save_kwargs)
            except Exception as e:
                self._handle_save_error(e, save_kwargs)
                if self.on_background_error is None:
                    raise
        else:
            try:
                self._submit_background_save(**save_kwargs)
            except Exception as e:
                self._handle_save_error(e, save_kwargs)
                if self.on_background_error is None:
                    raise

        # [ADD] 保存後に自動クリーンアップのトリガー判定
        # ベストエフォート: エビクション失敗がユーザーの関数結果に影響しないようにする
        try:
            self._trigger_auto_eviction()
        except Exception as e:
            logger.warning(f"Auto-eviction trigger failed (ignored): {e}")

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

        func_identifier = self._get_func_identifier(func)
        iid, ck = self._make_cache_key(
            func_identifier, args, kwargs, effective_key_fn, s_ver
        )
        loop = asyncio.get_running_loop()
        # async パスでは常にエグゼキュータが必要なので遅延初期化
        _, executor = self._ensure_bg_resources()

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
            executor, self._check_cache_sync, ck, serializer
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
        expires_at = self._calculate_expires_at(func_identifier, func.__name__, retention)

        save_kwargs = {
            "cache_key": ck,
            "func_name": func.__name__,
            "func_identifier": func_identifier,
            "input_id": str(iid),
            "version": s_ver,
            "result": res,
            "content_type": s_ct,
            "save_blob": s_blob,
            "serializer": serializer,
            "expires_at": expires_at,
        }

        if s_wait:
            try:
                await loop.run_in_executor(
                    executor,
                    functools.partial(self._save_result_sync, **save_kwargs),
                )
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                self._handle_save_error(e, save_kwargs)
                if self.on_background_error is None:
                    raise
        else:
            try:
                self._submit_background_save(**save_kwargs)
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                self._handle_save_error(e, save_kwargs)
                if self.on_background_error is None:
                    raise

        # [ADD] 保存後に自動クリーンアップのトリガー判定
        # ベストエフォート: エビクション失敗がユーザーの関数結果に影響しないようにする
        try:
            self._trigger_auto_eviction()
        except Exception as e:
            logger.warning(f"Auto-eviction trigger failed (ignored): {e}")

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
                except Exception as e:
                    logger.error(
                        f"Failed to deserialize FILE blob for `{cache_key}`: {e}"
                    )
                    return CACHE_MISS

        return CACHE_MISS

    # --- バックグラウンド保存の投入 ---
    def _submit_background_save(self, **save_kwargs) -> None:
        """wait=False 時にバックグラウンドへ保存処理を投入する。"""
        if self._own_executor:
            bg_loop, _ = self._ensure_bg_resources()
            coro = self._save_result_async(**save_kwargs)
            try:
                future = bg_loop.submit(coro)
                if future is None:
                    coro.close()
                    self._notify_save_discarded(save_kwargs)
                    return
            except RuntimeError:
                coro.close()
                raise
        else:
            assert self._executor is not None
            future = self._executor.submit(self._save_result_safe, **save_kwargs)
        self._track_future(future)

    def _notify_save_discarded(self, save_kwargs: dict) -> None:
        """シャットダウンにより破棄された保存の警告ログとコールバック通知。"""
        func_name = save_kwargs.get("func_name", "unknown")
        logger.warning(
            f"Background save for '{func_name}' was discarded: "
            "background loop is shutting down."
        )
        if self.on_background_error:
            try:
                context = SaveErrorContext(
                    func_name=func_name,
                    cache_key=save_kwargs.get("cache_key", ""),
                    input_id=save_kwargs.get("input_id", ""),
                    version=save_kwargs.get("version"),
                    content_type=save_kwargs.get("content_type"),
                    save_blob=save_kwargs.get("save_blob"),
                    expires_at=save_kwargs.get("expires_at"),
                    result=save_kwargs.get("result"),
                )
                self.on_background_error(
                    RuntimeError(
                        f"Background save for '{func_name}' was discarded "
                        "because the background loop is shutting down."
                    ),
                    context,
                )
            except Exception as cb_err:
                logger.error(
                    f"Error in 'on_background_error' callback: {cb_err}",
                    exc_info=True,
                )

    def _handle_save_error(self, err: Exception, save_kwargs: dict) -> None:
        """保存失敗をログし、必要ならコールバックで通知する。"""
        func_name = save_kwargs.get("func_name", "unknown")
        logger.error(
            f"Cache save failed for '{func_name}' (ignored): {err}", exc_info=True
        )
        if self.on_background_error:
            try:
                context = SaveErrorContext(
                    func_name=func_name,
                    cache_key=save_kwargs.get("cache_key", ""),
                    input_id=save_kwargs.get("input_id", ""),
                    version=save_kwargs.get("version"),
                    content_type=save_kwargs.get("content_type"),
                    save_blob=save_kwargs.get("save_blob"),
                    expires_at=save_kwargs.get("expires_at"),
                    result=save_kwargs.get("result"),
                )
                self.on_background_error(err, context)
            except Exception as cb_err:
                logger.error(
                    f"Error in 'on_background_error' callback: {cb_err}",
                    exc_info=True,
                )

    async def _save_result_async(self, /, **kwargs) -> None:
        """バックグラウンドループで実行される保存コルーチン。"""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            self._executor, functools.partial(self._save_result_safe, **kwargs)
        )

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
        func_identifier: Optional[str],
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
            func_identifier=func_identifier,
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
