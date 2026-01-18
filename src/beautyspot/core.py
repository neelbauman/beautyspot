# src/beautyspot/core.py

import hashlib
import logging
import functools
import inspect
import asyncio
import weakref
from concurrent.futures import ThreadPoolExecutor, Executor
from pathlib import Path  # Added Path
from typing import Any, Callable, Optional, Union, Type, overload, TypeVar

# Python 3.10+ では typing.ParamSpec が使えますが、
# ライブラリの互換性を考慮して typing_extensions を使うか、バージョン分岐します
try:
    from typing import ParamSpec
except ImportError:
    from typing_extensions import ParamSpec

from .limiter import TokenBucket
from .storage import BlobStorageBase, create_storage
from .db import TaskDB, SQLiteTaskDB
from .serializer import MsgpackSerializer, SerializationError
from .cachekey import KeyGen

# ジェネリクスの定義
P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# --- 追加: キャッシュミスを表す番兵オブジェクト ---
CACHE_MISS = object()


class Spot:
    """
    Spot class that handles task management, serialization, and
    resource management for marked functions including caching and storage.
    """

    def __init__(
        self,
        name: str,
        db: str | TaskDB | None = None,
        storage_path: str | None = None,  # Changed default to None
        s3_opts: dict | None = None,
        tpm: int = 10000,
        io_workers: int = 4,
        blob_warning_threshold: int = 1024 * 1024,
        executor: Optional[Executor] = None,
        storage: Optional[BlobStorageBase] = None,
        # --- Default Task Settings ---
        default_save_blob: bool = False,
        default_version: str | None = None,
        default_content_type: str | None = None,
    ):
        """
        Initialize a Spot instance.

        Args:
            name: Name of the spot/workspace.
            db: Database for tasks, can be a filepath or TaskDB instance.
            storage_path: Path for storing blobs locally.
            s3_opts: Options for S3 storage.
            tpm: Tokens per minute for rate limiting.
            io_workers: Number of IO workers for executor.
            blob_warning_threshold: Threshold size (bytes) to warn when saving large data to SQLite.
            executor: Optional pre-created executor.
            storage: Optional pre-created storage instance.
            default_save_blob: Default value for save_blob in mark/run.
            default_version: Default version string for mark/run.
            default_content_type: Default content_type for mark/run.
        """
        self.name = name
        self.blob_warning_threshold = blob_warning_threshold
        
        # Store defaults
        self.default_save_blob = default_save_blob
        self.default_version = default_version
        self.default_content_type = default_content_type

        # --- Workspace Setup ---
        # プロジェクト用の隠しディレクトリを用意
        self.workspace_dir = Path(".beautyspot")
        self._setup_workspace()

        # --- キャッシュ管理用 テーブル確認と初期化 ---
        if db is None:
            # デフォルトは隠しディレクトリ内のDBファイル
            self.db = SQLiteTaskDB(str(self.workspace_dir / f"{name}.db"))
        elif isinstance(db, str):
            self.db = SQLiteTaskDB(db)
        elif isinstance(db, TaskDB):
            self.db = db
        else:
            raise TypeError(
                "Argument 'db' must be a string (path) or a TaskDB instance."
            )
        self.db.init_schema()

        # --- Rate Limiter ---
        self.bucket = TokenBucket(tpm)

        # --- Serializer Setup ---
        self.serializer = MsgpackSerializer()

        # --- Storage 初期化 ---
        if storage is not None:
            self.storage = storage
        else:
            # storage_pathが未指定なら、隠しディレクトリ内のblobsを使う
            if storage_path is None:
                final_storage_path = str(self.workspace_dir / "blobs")
            else:
                final_storage_path = storage_path
            
            self.storage = create_storage(final_storage_path, s3_opts)

        # -- Executor Management ---
        if executor is not None:
            self.executor = executor
            self._own_executor = False
        else:
            self.executor = ThreadPoolExecutor(max_workers=io_workers)
            self._own_executor = True

            # 自動クリーンアップの登録
            # selfへの強い参照を持たせないよう、executorオブジェクトだけを残すこと
            self._finalizer = weakref.finalize(
                self, Spot._shutdown_executor, self.executor,
            )

    def _setup_workspace(self):
        """Ensure the workspace directory and .gitignore exist."""
        if not self.workspace_dir.exists():
            self.workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Add a .gitignore to ignore everything in this directory
        gitignore_path = self.workspace_dir / ".gitignore"
        if not gitignore_path.exists():
            with open(gitignore_path, "w") as f:
                f.write("*\n")

    # (以下、メソッドは変更なし)
    @staticmethod
    def _shutdown_executor(executor: Executor):
        """
        Clean-up function for internal Executor.
        ! This method must be a staticmethod to avoid circuler reference in weakrf.finalize() in self.__init__().

        Args:
            executor: The executor to be shut down.
        """
        executor.shutdown(wait=True)

    def shutdown(self, wait: bool = True):
        """
        Manually release resources.

        Args:
            wait: Whether to wait for the executor to be shut down.
        """
        if self._own_executor and self._finalizer.alive:
            self._finalizer()

    def __enter__(self) -> "Spot":
        """
        Enter the runtime context related to this object.

        Returns:
            self: The project instance itself.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Exit the runtime context and clean up resources.

        Args:
            exc_type: Exception type.
            exc_value: Exception value.
            traceback: Traceback object.
        """
        self.shutdown()

    def register_type(
        self, type_: Type, code: int, encoder: Callable, decoder: Callable
    ):
        """
        Register a custom type for serialization (Msgpack Extension Type).

        Args:
            type_: The class to handle (e.g. MyClass)
            code: Unique integer ID (0-127) for this type
            encoder: Function that converts obj -> bytes
            decoder: Function that converts bytes -> obj
        """
        self.serializer.register(type_, code, encoder, decoder)

    # --- Core Logic (Sync) ---

    def _resolve_settings(
        self,
        save_blob: bool | None,
        version: str | None,
        content_type: str | None
    ) -> tuple[bool, str | None, str | None]:
        """
        Resolve settings based on arguments and project defaults.
        Priority: Argument > Project Default
        """
        final_save_blob = save_blob if save_blob is not None else self.default_save_blob
        final_version = version if version is not None else self.default_version
        final_content_type = content_type if content_type is not None else self.default_content_type
        return final_save_blob, final_version, final_content_type

    def _make_cache_key(
        self,
        func_name: str,
        args: tuple,
        kwargs: dict,
        input_key_fn: Optional[Callable],
        version: str | None
    ) -> tuple[str, str]:
        """Generate input_id and cache_key."""
        iid = (
            input_key_fn(*args, **kwargs)
            if input_key_fn
            else KeyGen.default(args, kwargs)
        )

        key_source = f"{func_name}:{iid}"
        if version:
            key_source += f":{version}"

        ck = hashlib.md5(key_source.encode()).hexdigest()
        return iid, ck

    def _execute_sync(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        save_blob: bool | None,
        input_key_fn: Optional[Callable],
        version: str | None,
        content_type: Optional[str],
    ) -> Any:
        """Internal synchronous execution logic."""
        # Resolve Defaults
        s_blob, s_ver, s_ct = self._resolve_settings(save_blob, version, content_type)

        iid, ck = self._make_cache_key(func.__name__, args, kwargs, input_key_fn, s_ver)

        # 1. Check Cache
        cached = self._check_cache_sync(ck)
        if cached is not CACHE_MISS:
            return cached

        # 2. Execute
        res = func(*args, **kwargs)

        # 3. Save
        self._save_result_sync(
            ck, func.__name__, str(iid), s_ver, res, s_ct, s_blob
        )
        return res

    async def _execute_async(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        save_blob: bool | None,
        input_key_fn: Optional[Callable],
        version: str | None,
        content_type: Optional[str],
    ) -> Any:
        """Internal asynchronous execution logic."""
        # Resolve Defaults
        s_blob, s_ver, s_ct = self._resolve_settings(save_blob, version, content_type)

        iid, ck = self._make_cache_key(func.__name__, args, kwargs, input_key_fn, s_ver)
        loop = asyncio.get_running_loop()

        # 1. Check Cache (Offload IO)
        cached = await loop.run_in_executor(
            self.executor, self._check_cache_sync, ck
        )
        if cached is not CACHE_MISS:
            return cached

        # 2. Execute (Async)
        res = await func(*args, **kwargs)

        # 3. Save (Offload IO)
        await loop.run_in_executor(
            self.executor,
            self._save_result_sync,
            ck,
            func.__name__,
            str(iid),
            s_ver,
            res,
            s_ct,
            s_blob,
        )
        return res

    # --- Core Logic (Sync) ---
    def _check_cache_sync(self, cache_key: str) -> Any:
        entry = self.db.get(cache_key)

        if entry:
            r_type = entry["result_type"]
            r_val = entry["result_value"] # Path (str)
            r_data = entry.get("result_data")  # Content (bytes)

            # Case 1: Native SQLite BLOB (Standard for small data)
            if r_type == "DIRECT_BLOB":
                if r_data is None:
                    return CACHE_MISS  # データ破損時もMISS扱い
                    return None
                try:
                    return self.serializer.loads(r_data)
                except Exception as e:
                    logger.error(
                        f"Failed to deserialize DIRECT_BLOB for `{cache_key}`: {e}"
                    )
                    return CACHE_MISS

            # Case 2: External Blob (Standard for large data)
            elif r_type == "FILE":
                try:
                    # result_value is treated strictly as a Path/URI
                    data_bytes = self.storage.load(r_val)
                    return self.serializer.loads(data_bytes)
                except Exception:
                    return CACHE_MISS
        
        return CACHE_MISS  # エントリがない場合はMISS

    # ... (以下のメソッドは変更なし) ...
    def _save_result_sync(self, cache_key, func_name, input_id, version, result, content_type, save_blob):
        try:
            data_bytes = self.serializer.dumps(result)
        except SerializationError as e:
            # Fail fast if the type is not registered.
            raise e

        r_val = None
        r_blob = None
        r_type = "DIRECT_BLOB"

        if save_blob:
            # Explicit Blob Storage
            r_val = self.storage.save(cache_key, data_bytes)
            r_type = "FILE"
        else:
            # SQLite BLOB Storage
            data_size = len(data_bytes)

            # Guardrail: Warning for unintentional large data
            if data_size > self.blob_warning_threshold:
                logger.warning(
                    f"⚠️ Large data detected ({data_size / 1024:.1f} KB) for task '{func_name}'. "
                    f"This is saved to SQLite directly, which may bloat the database file. "
                    f"Consider adding `@spot.mark(save_blob=True)` to improve performance and file size."
                )

            # Save raw bytes
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
        )

    # --- Decorators ---

    def limiter(self, cost: Union[int, Callable] = 1):
        """
        Rate Limiting Decorator.

        Args:
            cost: Cost associated with the function, can be an int or a callable that returns an int.
        """

        def decorator(func):
            is_async = inspect.iscoroutinefunction(func)

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                c = cost(*args, **kwargs) if callable(cost) else cost
                self.bucket.consume(c)
                return func(*args, **kwargs)

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                c = cost(*args, **kwargs) if callable(cost) else cost
                await self.bucket.consume_async(c)
                return await func(*args, **kwargs)

            return async_wrapper if is_async else sync_wrapper

        return decorator

    # ----------------------------------------------------------------
    # Overload 1: @spot.mark として直接使用する場合
    # ----------------------------------------------------------------
    @overload
    def mark(self, _func: Callable[P, R]) -> Callable[P, R]:
        ...

    # ----------------------------------------------------------------
    # Overload 2: @spot.mark(save_blob=True) として使用する場合
    # ----------------------------------------------------------------
    @overload
    def mark(
        self,
        *,
        save_blob: Optional[bool] = None,
        input_key_fn: Optional[Callable] = None,
        version: str | None = None,
        content_type: Optional[str] = None,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        ...

    # ----------------------------------------------------------------
    # 実装 (Implementation)
    # ----------------------------------------------------------------
    def mark(
        self,
        _func: Optional[Callable] = None,
        *,
        save_blob: Optional[bool] = None,
        input_key_fn: Optional[Callable] = None,
        version: str | None = None,
        content_type: Optional[str] = None,
    ) -> Any:
        """
        Mark a function as a managed spot (Resumable Task Decorator).
        If arguments are None, they fall back to Spot defaults.

        Args:
            save_blob: If True, saves result using Storage (msgpack). If False, saves to DB directly.
            input_key_fn: Custom function to generate input ID from args/kwargs.
            version: Explicit version string. Change this to invalidate old cache entries.
        """
        if save_blob is None:
            save_blob = self.default_save_blob

        def decorator(func):
            is_async = inspect.iscoroutinefunction(func)

            # Key Gen Helper
            def make_key(args, kwargs):
                from .cachekey import KeyGen

                iid = (
                    input_key_fn(*args, **kwargs)
                    if input_key_fn
                    else KeyGen.default(args, kwargs)
                )

                key_source = f"{func.__name__}:{iid}"
                if version:
                    key_source += f":{version}"

                ck = hashlib.md5(key_source.encode()).hexdigest()
                return iid, ck

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                iid, ck = make_key(args, kwargs)

                # 1. Check Cache
                cached = self._check_cache_sync(ck)
                if cached is not CACHE_MISS:
                    return cached

                # 2. Execute
                res = func(*args, **kwargs)

                # 3. Save
                self._save_result_sync(
                    ck, func.__name__, str(iid), version, res, content_type, save_blob
                )
                return res

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                iid, ck = make_key(args, kwargs)
                loop = asyncio.get_running_loop()

                # 1. Check Cache (Offload IO)
                cached = await loop.run_in_executor(
                    self.executor, self._check_cache_sync, ck
                )
                if cached is not CACHE_MISS:
                    return cached

                # 2. Execute (Async)
                res = await func(*args, **kwargs)

                # 3. Save (Offload IO)
                await loop.run_in_executor(
                    self.executor,
                    self._save_result_sync,
                    ck,
                    func.__name__,
                    str(iid),
                    version,
                    res,
                    content_type,
                    save_blob,
                )
                return res

            return async_wrapper if is_async else sync_wrapper

        # ケース1: @spot.mark として呼ばれた場合
        # _func にデコレート対象の関数が入ってくる
        if _func is not None and callable(_func):
            return decorator(_func)

        # ケース2: @spot.mark(save_blob=True) として呼ばれた場合
        # _func は None になり、decorator自体を返す（その後Pythonがfuncを入れて呼んでくれる）
        return decorator

    # --- Imperative Execution ---

    def run(
        self,
        func: Callable,
        *args,
        _save_blob: Optional[bool] = None,
        _input_key_fn: Optional[Callable] = None,
        _version: str | None = None,
        _content_type: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """
        Execute a function with caching enabled.
        Arguments starting with '_' are configuration options.
        If options are None, they fall back to Project defaults.
        """
        if inspect.iscoroutinefunction(func):
            return self._execute_async(
                func, args, kwargs, _save_blob, _input_key_fn, _version, _content_type
            )
        else:
            return self._execute_sync(
                func, args, kwargs, _save_blob, _input_key_fn, _version, _content_type
            )
