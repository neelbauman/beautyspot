"""BeautySpot コアモジュール。

タスク管理、シリアライズ、キャッシュとストレージを含むリソース管理を行うメインクラス群を提供します。
"""
# src/beautyspot/core.py

import atexit
import asyncio
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
from typing import (
    Any,
    Coroutine,
    Callable,
    Iterator,
    NamedTuple,
    Optional,
    Union,
    Type,
    overload,
    TypeVar,
    TypeVarTuple,
    ParamSpec,
    Sequence,
    ContextManager,
)

from beautyspot.maintenance import MaintenanceService
from beautyspot.limiter import LimiterProtocol
from beautyspot.types import SaveErrorContext
from beautyspot.lifecycle import (
    RetentionSpec,
)
from beautyspot.db import TaskDBCore, Flushable, Shutdownable
from beautyspot.serializer import SerializerProtocol, TypeRegistryProtocol
from beautyspot.cachekey import KeyGenPolicy
from beautyspot.exceptions import (
    ConfigurationError,
    IncompatibleProviderError,
    ValidationError,
)
from beautyspot.hooks import HookBase
from beautyspot.types import PreExecuteContext, CacheHitContext, CacheMissContext
from beautyspot.content_types import ContentType
from beautyspot.cache import CacheManager, CACHE_MISS

# ジェネリクスの定義
P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")
Ts = TypeVarTuple("Ts")

# --- ロガー ---
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class _ExecutionContext(NamedTuple):
    """_execute_sync / _execute_async の初期化フェーズで共通する解決済み値。"""

    save_blob: bool | None
    version: str | None
    content_type: str | None
    save_sync: bool
    func_identifier: str
    input_id: str
    cache_key: str
    hook_kwargs: dict


class _BackgroundLoop:
    """バックグラウンドで非同期IOタスクを処理するイベントループ。

    明示的なタスク追跡とスレッドロックにより、シャットダウン時の競合状態を完全に排除します。

    Args:
        drain_timeout (float, optional): シャットダウン時のタスク完了待機タイムアウト（秒）。デフォルトは5.0。
    """

    def __init__(self, drain_timeout: float = 5.0):
        self._drain_timeout = drain_timeout

        # メインスレッドで loop オブジェクトを生成
        self._loop = asyncio.new_event_loop()

        self._lock = threading.Lock()
        self._is_shutting_down = False
        self._active_tasks = 0  # 実行中（またはスケジュール待ち）のタスク数

        # 新しい Thread を設定
        # daemon=True により、プロセス終了時の Python の無限ハングアップを防ぐ
        self._thread = threading.Thread(
            target=self._run_event_loop, daemon=True, name="BeautySpot-BGLoop"
        )

        # 設定した Thread を実行
        self._thread.start()

        # インスタンス自身が atexit を管理するため、グローバルな _active_loops 管理は不要
        atexit.register(self._shutdown)

    def _run_event_loop(self):
        """スレッドローカルでイベントループを実行する"""
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
        except BaseException:
            # 万が一スケジュールに失敗した場合はカウンタを戻す
            try:
                coro.close()
            except Exception:
                pass
            with self._lock:
                self._active_tasks -= 1
                # シャットダウン中かつ最後のタスクだった場合、ループ停止を通知する
                if self._is_shutting_down and self._active_tasks == 0:
                    try:
                        self._loop.call_soon_threadsafe(self._loop.stop)
                    except RuntimeError:
                        pass  # ループは既に停止/クローズ済み
            raise

    def stop(self, save_sync: bool = True):
        """
        ループに対して新規タスクの受付停止を通知し、シャットダウンシーケンスを開始する。
        Spot.shutdown() や GCの _shutdown_resources() から呼び出される統一されたAPI。
        """
        # atexit ハンドラの蓄積を防止
        atexit.unregister(self._shutdown)

        with self._lock:
            # 既にシャットダウン中であれば二重実行を避ける
            if self._is_shutting_down:
                return
            self._is_shutting_down = True

            # 現在アクティブなタスクがゼロなら、即座にループ停止をスケジュール
            if self._active_tasks == 0:
                self._loop.call_soon_threadsafe(self._loop.stop)

        if save_sync:
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
        self.stop(save_sync=True)


class Spot:
    """タスク管理、シリアライズ、キャッシュとストレージを含むリソース管理を行うメインクラス。

    依存オブジェクト（CacheManagerやLimiterProtocolなど）を注入して初期化されます。
    通常は直接インスタンス化せず、`bs.Spot(...)` ファクトリ関数を通じて使用することが推奨されます。

    Args:
        name (str): Spotインスタンスの名前。
        cache (CacheManager): キャッシュマネージャーのインスタンス。
        limiter (LimiterProtocol): レートリミッターのインスタンス。
        save_sync (bool, optional): キャッシュ保存のデフォルト同期動作。デフォルトはTrue。
        eviction_rate (float, optional): キャッシュの自動破棄を実行する確率（0.0〜1.0）。デフォルトは0.0。
        drain_timeout (float, optional): バックグラウンドタスク完了待機のタイムアウト（秒）。デフォルトは5.0。
        drain_poll_interval (float, optional): バックグラウンドタスク待機時のポーリング間隔（秒）。デフォルトは0.5。
        on_background_error (Optional[Callable[[Exception, SaveErrorContext], None]], optional): バックグラウンド保存時のエラーハンドラ。
    """

    def __init__(
        self,
        name: str,
        cache: CacheManager,
        limiter: LimiterProtocol,
        save_sync: bool = True,
        eviction_rate: float = 0.0,
        drain_timeout: float = 5.0,
        drain_poll_interval: float = 0.5,
        on_background_error: Optional[
            Callable[[Exception | BaseException, SaveErrorContext], None]
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

        # --- コンポーネントの保持 ---
        self.cache = cache
        self.limiter = limiter

        # --- オプション設定の適用 ---
        self._save_sync = save_sync
        self.on_background_error = on_background_error

        # --- DBの初期化 ---
        self.cache.db.init_schema()

        # --- バックグラウンド IO 管理 ---
        self._bg_loop: _BackgroundLoop | None = None
        self._executor: Executor | None = None
        self._finalizer: weakref.finalize | None = None

        self._bg_init_lock = threading.Lock()
        self._shutdown_called = False
        self._owns_db = False

        self._active_futures: set = set()
        self._futures_lock = threading.Lock()

        self._maintenance_service: MaintenanceService | None = None
        self._maintenance_lock = threading.Lock()
        self._eviction_guard_lock = threading.Lock()
        self._eviction_running = False
        self._last_eviction_time = 0.0

    def __enter__(self) -> "Spot":
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._drain_futures()

    def _track_future(self, future: Any):
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
        svc = self._maintenance_service
        if svc is None:
            with self._maintenance_lock:
                if self._maintenance_service is None:
                    self._maintenance_service = MaintenanceService(
                        db=self.cache.db,
                        storage=self.cache.storage,
                        serializer=self.cache.serializer,
                    )
                svc = self._maintenance_service
        assert svc is not None
        return svc

    def _ensure_bg_resources(self) -> tuple[_BackgroundLoop, Executor]:
        bg, ex = self._bg_loop, self._executor
        if bg is not None and ex is not None:
            return bg, ex

        with self._bg_init_lock:
            if self._shutdown_called:
                raise RuntimeError(
                    "Cannot submit background tasks after shutdown() has been called."
                )
            if self._bg_loop is None or self._executor is None:
                if self._bg_loop is None:
                    self._bg_loop = _BackgroundLoop(drain_timeout=self._drain_timeout)
                if self._executor is None:
                    self._executor = ThreadPoolExecutor()
                if self._finalizer is None:
                    self._finalizer = weakref.finalize(
                        self,
                        Spot._shutdown_resources,
                        self._bg_loop,
                        self._executor,
                        self.cache.db,
                        self._owns_db,
                    )
                    self._finalizer.atexit = False
            return self._bg_loop, self._executor

    @staticmethod
    def _shutdown_resources(
        bg_loop: _BackgroundLoop,
        executor: Executor,
        db: TaskDBCore,
        owns_db: bool,
    ) -> None:
        bg_loop.stop(save_sync=False)
        executor.shutdown(wait=False, cancel_futures=True)
        if owns_db and isinstance(db, Shutdownable):
            db.shutdown(wait=False)

    def shutdown(self, save_sync: bool = True):
        """Spotインスタンスをシャットダウンし、バックグラウンドリソースを解放する。

        Args:
            save_sync (bool, optional): 同期的に未完了の保存タスクを待機するかどうか。Trueの場合は完了を待つ。デフォルトはTrue。
        """
        with self._bg_init_lock:
            self._shutdown_called = True
        if self._finalizer is not None and self._finalizer.alive:
            self._finalizer.detach()
        if save_sync:
            self._drain_futures()

        if self._bg_loop is not None:
            self._bg_loop.stop(save_sync=save_sync)

        if self._executor is not None:
            self._executor.shutdown(wait=save_sync, cancel_futures=not save_sync)

    def flush(self, timeout: Optional[float] = None) -> None:
        """バックグラウンドで実行中のすべての保存タスクとDBの書き込みの完了を待機する。

        Args:
            timeout (Optional[float], optional): 待機する最大時間（秒）。指定しない場合は初期化時の `drain_timeout` が使用される。
        """
        timeout_val = timeout if timeout is not None else self._drain_timeout
        deadline = time.monotonic() + timeout_val

        while True:
            with self._futures_lock:
                snapshot = list(self._active_futures)
            if not snapshot:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            wait_timeout = min(self._drain_poll_interval, remaining)
            wait(snapshot, timeout=wait_timeout)

        db_remaining = deadline - time.monotonic()
        if db_remaining > 0 and isinstance(self.cache.db, Flushable):
            self.cache.db.flush(timeout=db_remaining)

    def _drain_futures(self) -> None:
        self.flush()

    def _get_func_identifier(self, func: Callable) -> str:
        module = getattr(func, "__module__", None) or func.__class__.__module__
        qualname = getattr(func, "__qualname__", None) or func.__class__.__qualname__
        return f"{module}.{qualname}"

    def _trigger_auto_eviction(self) -> None:
        if self.eviction_rate <= 0.0:
            return
        if random.random() >= self.eviction_rate:
            return

        with self._eviction_guard_lock:
            if self._eviction_running:
                return
            now = time.monotonic()
            if now - self._last_eviction_time < 60.0:
                return
            self._eviction_running = True

        logger.debug(f"Triggering auto-eviction (rate: {self.eviction_rate})")

        with self._futures_lock:
            pending_futures = list(self._active_futures)

        def _run_clean_safe():
            try:
                self.maintenance.clean_garbage(orphan_grace_seconds=60.0)
            except Exception as e:
                logger.error(f"Auto-eviction failed: {e}", exc_info=True)

        def _clear_eviction_flag():
            with self._eviction_guard_lock:
                self._last_eviction_time = time.monotonic()
                self._eviction_running = False

        try:
            bg_loop, executor = self._ensure_bg_resources()

            async def _run_clean_coro():
                loop = asyncio.get_running_loop()
                if pending_futures:
                    await asyncio.wait(
                        [asyncio.wrap_future(f) for f in pending_futures],
                        timeout=self._drain_timeout,
                    )
                await loop.run_in_executor(executor, _run_clean_safe)

            future = bg_loop.submit(_run_clean_coro())
            if future:
                self._track_future(future)
                future.add_done_callback(lambda f: _clear_eviction_flag())
            else:
                _clear_eviction_flag()
        except Exception:
            _clear_eviction_flag()

    def _resolve_key_fn(
        self,
        func: Callable,
        keygen: Optional[Union[Callable, KeyGenPolicy]] = None,
        input_key_fn: Optional[Union[Callable, KeyGenPolicy]] = None,
    ) -> Optional[Callable]:
        if keygen is not None and input_key_fn is not None:
            raise IncompatibleProviderError("Cannot specify both 'keygen' and 'input_key_fn'.")
        if input_key_fn is not None:
            warnings.warn("`input_key_fn` is deprecated, use `keygen` instead.", DeprecationWarning, stacklevel=3)
        target = keygen or input_key_fn
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
        """カスタム型をシリアライザに登録するためのデコレータ。

        `decoder` または `decoder_factory` のいずれかを必ず提供する必要があります。

        Args:
            code (int): カスタム型の一意な識別コード。
            encoder (Callable[[T], Any]): カスタム型オブジェクトからシリアライズ可能な形式（辞書など）に変換する関数。
            decoder (Optional[Callable[[Any], T]], optional): デシリアライズ時にデータをカスタム型オブジェクトに復元する関数。
            decoder_factory (Optional[Callable[[Type[T]], Callable[[Any], T]]], optional): 型に基づいてデコーダ関数を生成するファクトリ関数。

        Returns:
            Callable[[Type[T]], Type[T]]: クラスデコレータ。

        Raises:
            IncompatibleProviderError: `decoder` と `decoder_factory` の両方が未指定の場合に発生。
        """
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
        """カスタム型を直接シリアライザに登録する。

        Args:
            type_class (Type[T]): 登録するカスタム型のクラス。
            code (int): カスタム型の一意な識別コード。
            encoder (Callable[[T], Any]): エンコーダ関数。
            decoder (Callable[[Any], T]): デコーダ関数。

        Raises:
            NotImplementedError: 現在のシリアライザが型登録をサポートしていない場合。
        """
        if isinstance(self.cache.serializer, TypeRegistryProtocol):
            self.cache.serializer.register(type_class, code, encoder, decoder)
        else:
            raise NotImplementedError(
                "Current serializer does not support type registration."
            )

    @staticmethod
    def _dispatch_hooks(
        hooks: Optional[Sequence[HookBase]], method_name: str, context: Any
    ) -> None:
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

    async def _dispatch_hooks_async(
        self,
        hooks: Optional[Sequence[HookBase]],
        method_name: str,
        context: Any,
        loop: asyncio.AbstractEventLoop,
        executor: Executor,
    ) -> None:
        if not hooks:
            return
        await loop.run_in_executor(
            executor, self._dispatch_hooks, hooks, method_name, context
        )

    # --- Core Logic ---

    def _resolve_settings(
        self,
        save_blob: bool | None,
        version: str | None,
        content_type: str | ContentType | None,
        save_sync: bool | None,
    ) -> tuple[bool | None, str | None, str | None, bool]:
        return (
            save_blob,
            version,
            content_type,
            (save_sync if save_sync is not None else self._save_sync),
        )

    def _prepare_execution(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        save_blob: bool | None,
        effective_key_fn: Optional[Callable],
        version: str | None,
        content_type: Optional[str | ContentType],
        save_sync: bool | None,
        hooks: Optional[Sequence[HookBase]],
    ) -> _ExecutionContext:
        s_blob, s_ver, s_ct, s_save_sync = self._resolve_settings(
            save_blob, version, content_type, save_sync
        )
        func_identifier = self._get_func_identifier(func)
        iid, ck = self.cache.make_cache_key(
            func_identifier, args, kwargs, effective_key_fn, s_ver
        )
        return _ExecutionContext(
            s_blob,
            s_ver,
            s_ct,
            s_save_sync,
            func_identifier,
            iid,
            ck,
            dict(kwargs) if hooks else kwargs,
        )

    def _build_cache_hit_context(
        self,
        func_name: str,
        input_id: str,
        cache_key: str,
        args: tuple,
        hook_kwargs: dict,
        result: Any,
        version: str | None,
    ) -> CacheHitContext:
        return CacheHitContext(
            func_name=func_name,
            input_id=str(input_id),
            cache_key=cache_key,
            args=args,
            kwargs=hook_kwargs,
            result=result,
            version=version,
        )

    def _build_save_kwargs(
        self,
        cache_key: str,
        func: Callable,
        func_identifier: str,
        input_id: str,
        version: str | None,
        result: Any,
        content_type: str | None,
        save_blob: bool | None,
        serializer: Optional[SerializerProtocol],
        retention: RetentionSpec,
    ) -> dict:
        expires_at = self.cache.calculate_expires_at(
            func_identifier, func.__name__, retention
        )
        return {
            "cache_key": cache_key,
            "func_name": func.__name__,
            "func_identifier": func_identifier,
            "input_id": str(input_id),
            "version": version,
            "result": result,
            "content_type": content_type,
            "save_blob": save_blob,
            "serializer": serializer,
            "expires_at": expires_at,
        }

    def _persist_result_sync(self, save_sync: bool, save_kwargs: dict) -> None:
        if save_sync:
            try:
                self.cache.set(**save_kwargs)
            except Exception as e:
                self._handle_save_error(e, save_kwargs)
                raise
        else:
            try:
                self._submit_background_save(**save_kwargs)
            except Exception as e:
                self._handle_save_error(e, save_kwargs)
                if self.on_background_error is None:
                    raise

    async def _persist_result_async(self, save_sync: bool, save_kwargs: dict) -> None:
        if save_sync:
            try:
                bg_loop, exec_pool = self._ensure_bg_resources()
                coro = self._save_result_async(
                    executor=exec_pool, safe=False, **save_kwargs
                )
                future = bg_loop.submit(coro)
                if future is None:
                    self._notify_save_discarded(save_kwargs)
                    raise RuntimeError(
                        f"Cache save for '{save_kwargs.get('func_name')}' "
                        "was discarded because the background loop is shutting down."
                    )
                else:
                    await asyncio.wrap_future(future)
            except Exception as e:
                self._handle_save_error(e, save_kwargs)
                raise
        else:
            try:
                self._submit_background_save(**save_kwargs)
            except Exception as e:
                self._handle_save_error(e, save_kwargs)
                if self.on_background_error is None:
                    raise

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
        retention: RetentionSpec,
        save_sync: bool | None,
        hooks: Optional[Sequence[HookBase]] = None,
    ) -> Any:
        ctx = self._prepare_execution(
            func,
            args,
            kwargs,
            save_blob,
            effective_key_fn,
            version,
            content_type,
            save_sync,
            hooks,
        )
        self._dispatch_hooks(
            hooks,
            "pre_execute",
            PreExecuteContext(
                func.__name__, str(ctx.input_id), ctx.cache_key, args, ctx.hook_kwargs
            ),
        )
        cached = self.cache.get(ctx.cache_key, serializer)
        if cached is not CACHE_MISS:
            self._dispatch_hooks(
                hooks,
                "on_cache_hit",
                self._build_cache_hit_context(
                    func.__name__,
                    ctx.input_id,
                    ctx.cache_key,
                    args,
                    ctx.hook_kwargs,
                    cached,
                    ctx.version,
                ),
            )
            return cached
        herd = self.cache.wait_herd_sync(ctx.cache_key, serializer)
        if not herd.is_executor:
            if herd.is_error:
                raise herd.result
            self._dispatch_hooks(
                hooks,
                "on_cache_hit",
                self._build_cache_hit_context(
                    func.__name__,
                    ctx.input_id,
                    ctx.cache_key,
                    args,
                    ctx.hook_kwargs,
                    herd.result,
                    ctx.version,
                ),
            )
            return herd.result
        try:
            res = func(*args, **kwargs)
            self._dispatch_hooks(
                hooks,
                "on_cache_miss",
                CacheMissContext(
                    func.__name__,
                    str(ctx.input_id),
                    ctx.cache_key,
                    args,
                    ctx.hook_kwargs,
                    res,
                    ctx.version,
                ),
            )
            herd.result_box.append((True, res))
            
            # 実行成功後、同期モード(save_sync=True)の場合はキャッシュ保存エラーを伝播させる
            try:
                save_kwargs = self._build_save_kwargs(
                    ctx.cache_key,
                    func,
                    ctx.func_identifier,
                    ctx.input_id,
                    ctx.version,
                    res,
                    ctx.content_type,
                    ctx.save_blob,
                    serializer,
                    retention,
                )
                self._persist_result_sync(ctx.save_sync, save_kwargs)
            except Exception as e:
                if ctx.save_sync:
                    raise
                logger.error(f"Failed to submit background cache save, but execution succeeded: {e}")
                
            return res

        except BaseException as e:
            if not herd.result_box:
                herd.result_box.append((False, e))
            raise
        finally:
            self.cache.notify_and_cleanup_inflight(
                ctx.cache_key, herd.event, herd.result_box
            )
            self._trigger_auto_eviction()

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
        retention: RetentionSpec,
        save_sync: bool | None,
        hooks: Optional[Sequence[HookBase]] = None,
    ) -> Any:
        ctx = self._prepare_execution(
            func,
            args,
            kwargs,
            save_blob,
            effective_key_fn,
            version,
            content_type,
            save_sync,
            hooks,
        )
        loop = asyncio.get_running_loop()
        _, executor = self._ensure_bg_resources()
        await self._dispatch_hooks_async(
            hooks,
            "pre_execute",
            PreExecuteContext(
                func.__name__, str(ctx.input_id), ctx.cache_key, args, ctx.hook_kwargs
            ),
            loop,
            executor,
        )
        cached = await loop.run_in_executor(
            executor, self.cache.get, ctx.cache_key, serializer
        )
        if cached is not CACHE_MISS:
            await self._dispatch_hooks_async(
                hooks,
                "on_cache_hit",
                self._build_cache_hit_context(
                    func.__name__,
                    ctx.input_id,
                    ctx.cache_key,
                    args,
                    ctx.hook_kwargs,
                    cached,
                    ctx.version,
                ),
                loop,
                executor,
            )
            return cached
        herd = await self.cache.wait_herd_async(
            ctx.cache_key, serializer, loop, executor
        )
        if not herd.is_executor:
            if herd.is_error:
                raise herd.result
            await self._dispatch_hooks_async(
                hooks,
                "on_cache_hit",
                self._build_cache_hit_context(
                    func.__name__,
                    ctx.input_id,
                    ctx.cache_key,
                    args,
                    ctx.hook_kwargs,
                    herd.result,
                    ctx.version,
                ),
                loop,
                executor,
            )
            return herd.result
        try:
            res = await func(*args, **kwargs)
            await self._dispatch_hooks_async(
                hooks,
                "on_cache_miss",
                CacheMissContext(
                    func.__name__,
                    str(ctx.input_id),
                    ctx.cache_key,
                    args,
                    ctx.hook_kwargs,
                    res,
                    ctx.version,
                ),
                loop,
                executor,
            )
            herd.result_box.append((True, res))
            
            # 実行成功後、同期モード(save_sync=True)の場合はキャッシュ保存エラーを伝播させる
            try:
                save_kwargs = self._build_save_kwargs(
                    ctx.cache_key,
                    func,
                    ctx.func_identifier,
                    ctx.input_id,
                    ctx.version,
                    res,
                    ctx.content_type,
                    ctx.save_blob,
                    serializer,
                    retention,
                )
                await self._persist_result_async(ctx.save_sync, save_kwargs)
            except Exception as e:
                if ctx.save_sync:
                    raise
                logger.error(f"Failed to persist cache asynchronously, but execution succeeded: {e}")

            return res

        except BaseException as e:
            if not herd.result_box:
                herd.result_box.append((False, e))
            raise
        finally:
            self.cache.notify_and_cleanup_inflight(
                ctx.cache_key, herd.event, herd.result_box
            )
            self._trigger_auto_eviction()

    def _handle_save_error(self, err: BaseException | Exception, save_kwargs: dict) -> None:
        logger.error(
            f"Cache save failed for '{save_kwargs.get('func_name')}': {err}",
            exc_info=True,
        )
        if self.on_background_error:
            try:
                import sys

                res = save_kwargs.get("result")
                self.on_background_error(
                    err,
                    SaveErrorContext(
                        func_name=save_kwargs.get("func_name", "unknown"),
                        cache_key=save_kwargs.get("cache_key", ""),
                        input_id=save_kwargs.get("input_id", ""),
                        version=save_kwargs.get("version"),
                        content_type=save_kwargs.get("content_type"),
                        save_blob=save_kwargs.get("save_blob"),
                        expires_at=save_kwargs.get("expires_at"),
                        result_type=type(res).__name__,
                        result_size=sys.getsizeof(res) if res is not None else None,
                    ),
                )
            except Exception:
                logger.error(
                    "Error occurred within the 'on_background_error' callback",
                    exc_info=True,
                )

    def _notify_save_discarded(self, save_kwargs: dict) -> None:
        msg = f"Background save for '{save_kwargs.get('func_name')}' discarded during shutdown."
        logger.warning(msg)
        warnings.warn(msg, ResourceWarning)
        self._handle_save_error(RuntimeError(msg), save_kwargs)

    def _submit_background_save(self, **save_kwargs) -> None:
        bg_loop, executor = self._ensure_bg_resources()
        coro = self._save_result_async(executor=executor, **save_kwargs)
        future = bg_loop.submit(coro)
        if future:
            self._track_future(future)
        else:
            self._notify_save_discarded(save_kwargs)

    async def _save_result_async(
        self, /, executor: Executor, safe: bool = True, **kwargs
    ) -> None:
        loop = asyncio.get_running_loop()
        target = (lambda **kw: self._save_result_safe(**kw)) if safe else self.cache.set
        try:
            await loop.run_in_executor(executor, functools.partial(target, **kwargs))
        except (asyncio.CancelledError, RuntimeError) as e:
            # Executor might be forcibly shut down during program exit or Spot.shutdown(save_sync=False)
            msg = f"Background save for '{kwargs.get('func_name')}' cancelled during shutdown."
            logger.warning(msg)
            self._handle_save_error(e, kwargs)
            if not safe:
                raise

    def _save_result_safe(self, **kwargs):
        try:
            self.cache.set(**kwargs)
        except Exception as e:
            self._handle_save_error(e, kwargs)

    def consume(self, cost: Union[int, Callable] = 1):
        """関数実行前にレートリミッターのトークンを消費するデコレータ。

        Args:
            cost (Union[int, Callable], optional): 消費するコスト。整数、または実行時の引数を受け取りコストを計算する関数を指定可能。デフォルトは1。

        Returns:
            Callable: デコレートされた関数。
        """
        def decorator(func):
            is_async = inspect.iscoroutinefunction(func)

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                self.limiter.consume(cost(*args, **kwargs) if callable(cost) else cost)
                return func(*args, **kwargs)

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                await self.limiter.consume_async(
                    cost(*args, **kwargs) if callable(cost) else cost
                )
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
        save_sync: Optional[bool] = None,
        retention: RetentionSpec = None,
        hooks: Optional[Sequence[HookBase]] = None,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]: ...

    def mark(self, _func: Optional[Callable] = None, **kwargs) -> Any:
        """関数を修飾し、実行結果のキャッシュ機能とメタデータ管理を追加するデコレータ。

        関数の実行結果は、引数とその他の設定から計算されたキャッシュキーに基づいて保存・再利用されます。

        Args:
            _func (Optional[Callable], optional): デコレート対象の関数。
            save_blob (Optional[bool], optional): 大きな戻り値をBlobストレージに保存するかどうか。
            keygen (Optional[Union[Callable, KeyGenPolicy]], optional): キャッシュキーの生成ロジックを指定する。
            input_key_fn (Optional[Union[Callable, KeyGenPolicy]], optional): 非推奨。`keygen` を使用すること。
            version (Optional[str], optional): 関数のキャッシュバージョン。ロジック変更時にインクリメントすることでキャッシュを無効化できる。
            content_type (Optional[Union[str, ContentType]], optional): 戻り値のMIMEタイプ。
            serializer (Optional[SerializerProtocol], optional): この関数に適用するカスタムシリアライザ。
            save_sync (Optional[bool], optional): 保存処理を同期的に行うかどうか。
            retention (RetentionSpec, optional): キャッシュの保持ポリシー。
            hooks (Optional[Sequence[HookBase]], optional): 実行前後やキャッシュヒット時に発火するフックのリスト。

        Returns:
            Any: デコレートされた関数、またはデコレータ関数。
        """
        def decorator(func):
            if inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func):
                raise ConfigurationError(f"Generators not supported: {func.__name__}")
            key_fn = self._resolve_key_fn(
                func, kwargs.get("keygen"), kwargs.get("input_key_fn")
            )
            is_async = inspect.iscoroutinefunction(func)

            @functools.wraps(func)
            def sync_wrapper(*args, **kw):
                return self._execute_sync(
                    func,
                    args,
                    kw,
                    kwargs.get("save_blob"),
                    key_fn,
                    kwargs.get("version"),
                    kwargs.get("content_type"),
                    kwargs.get("serializer"),
                    kwargs.get("retention"),
                    kwargs.get("save_sync"),
                    kwargs.get("hooks"),
                )

            @functools.wraps(func)
            async def async_wrapper(*args, **kw):
                return await self._execute_async(
                    func,
                    args,
                    kw,
                    kwargs.get("save_blob"),
                    key_fn,
                    kwargs.get("version"),
                    kwargs.get("content_type"),
                    kwargs.get("serializer"),
                    kwargs.get("retention"),
                    kwargs.get("save_sync"),
                    kwargs.get("hooks"),
                )

            return async_wrapper if is_async else sync_wrapper

        return decorator(_func) if _func else decorator

    @overload
    def cached_run(self, __func: Callable[P, R], **kwargs: Any) -> ContextManager[Callable[P, R]]: ...

    @overload
    def cached_run(self, *funcs: *Ts, **kwargs: Any) -> ContextManager[tuple[*Ts]]: ...

    @contextmanager
    def cached_run(self, *funcs: Any, **kwargs) -> Iterator[Any]:
        """コンテキストマネージャ内で一時的に関数を `mark` し、キャッシュ機能を適用する。

        デコレータを直接付与できない外部ライブラリの関数などをキャッシュする際に使用します。

        Args:
            *funcs (Any): キャッシュ対象にする関数（複数可）。
            **kwargs: `mark` デコレータに渡すオプションパラメータ。

        Yields:
            Callable | tuple[Callable, ...]: キャッシュ機能が付与された関数。複数の場合はタプルで返る。

        Raises:
            ValidationError: 関数が1つも指定されなかった場合。
        """
        if not funcs:
            raise ValidationError(
                "At least one function must be provided to cached_run."
            )
        wrappers = [self.mark(**kwargs)(f) for f in funcs]
        yield wrappers[0] if len(wrappers) == 1 else tuple(wrappers)
