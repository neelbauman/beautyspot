# src/beautyspot/core.py

import hashlib
import logging
import functools
import inspect
import asyncio
import weakref
from concurrent.futures import ThreadPoolExecutor, Executor
from typing import Any, Callable, Optional, Union, Type

from .limiter import TokenBucket
from .storage import BlobStorageBase, create_storage
from .db import TaskDB, SQLiteTaskDB
from .serializer import MsgpackSerializer, SerializationError

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class Project:
    """
    Project class that handles task management, serialization, and
    resource management for tasks including caching and storage.
    """

    def __init__(
        self,
        name: str,
        db: str | TaskDB | None = None,
        storage_path: str = "./blobs",
        s3_opts: dict | None = None,
        tpm: int = 10000,
        io_workers: int = 4,
        blob_warning_threshold: int = 1024 * 1024,
        executor: Optional[Executor] = None,
        storage: Optional[BlobStorageBase] = None,
    ):
        """
        Initialize a Project instance.

        Args:
            name: Name of the project.
            db: Database for tasks, can be a filepath or TaskDB instance.
            storage_path: Path for storing blobs locally.
            s3_opts: Options for S3 storage.
            tpm: Tokens per minute for rate limiting.
            io_workers: Number of IO workers for executor.
            blob_warning_threshold: Threshold size (bytes) to warn when saving large data to SQLite.
            executor: Optional pre-created executor.
            storage: Optional pre-created storage instance.
        """
        self.name = name
        self.blob_warning_threshold = blob_warning_threshold

        if db is None:
            self.db = SQLiteTaskDB(f"{name}.db")
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

        # --- Storage Selection ---
        if storage is not None:
            self.storage = storage
        else:
            self.storage = create_storage(storage_path, s3_opts)

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
                self, Project._shutdown_executor, self.executor,
            )

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

    def __enter__(self):
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
    def _check_cache_sync(self, cache_key: str) -> Any:
        """
        Check the cache for a given key synchronously.

        Args:
            cache_key: The cache key to check.

        Returns:
            The cached result if available, otherwise None.
        """
        entry = self.db.get(cache_key)

        if entry:
            r_type = entry["result_type"]
            r_val = entry["result_value"] # Path (str)
            r_data = entry.get("result_data")  # Content (bytes)

            # Case 1: Native SQLite BLOB (Standard for small data)
            if r_type == "DIRECT_BLOB":
                if r_data is None:
                    logger.warning(f"Cache corrupted: DIRECT_BLOB found but data is NULL for `{cache_key}`.")
                    return None
                try:
                    return self.serializer.loads(r_data)
                except Exception as e:
                    logger.error(
                        f"Failed to deserialize DIRECT_BLOB for `{cache_key}`: {e}"
                    )
                    return None

            # Case 2: External Blob (Standard for large data)
            elif r_type == "FILE":
                try:
                    # result_value is treated strictly as a Path/URI
                    data_bytes = self.storage.load(r_val)
                    return self.serializer.loads(data_bytes)
                except FileNotFoundError:
                    logger.warning(
                        f"Cache blob missing for key {cache_key}. Re-computing."
                    )
                    return None
                except (ValueError, SerializationError) as e:
                    logger.warning(
                        f"⚠️ Cache corrupted or incompatible for '{cache_key}'. Re-computing...\n"
                        f"   Error: {e}"
                    )
                    return None
                except Exception as e:
                    logger.error(
                        f"Unexpected error loading cache for '{cache_key}': {e}"
                    )
                    return None
        return None

    def _save_result_sync(
        self,
        cache_key: str,
        func_name: str,
        input_id: str,
        version: str | None,
        result: Any,
        content_type: str | None,
        save_blob: bool,
    ):
        """
        Save a result synchronously.

        Args:
            cache_key: The cache key to save.
            func_name: The name of the function.
            input_id: The input ID.
            version: The version string for caching.
            result: The result to save.
            content_type: Type of content to be saved.
            save_blob: Whether to save as a blob or directly in DB.
        """
        # 1. Always Serialize with Msgpack first (Consistency)
        try:
            data_bytes = self.serializer.dumps(result)
        except SerializationError as e:
            # Fail fast if the type is not registered.
            raise e

        r_val = None
        r_blob = None

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
                    f"Consider adding `@project.task(save_blob=True)` to improve performance and file size."
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
            result_data=r_blob
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

    def task(
        self,
        _func: Optional[Callable] = None,
        *,
        save_blob: bool = False,
        input_key_fn: Optional[Callable] = None,
        version: str | None = None,
        content_type: Optional[str] = None,
    ):
        """
        Resumable Task Decorator.

        Args:
            save_blob: If True, saves result using Storage (pickle). If False, saves to DB directly (JSON).
            input_key_fn: Custom function to generate input ID from args/kwargs.
            version: Explicit version string. Change this to invalidate old cache entries.
        """

        def decorator(func):
            is_async = inspect.iscoroutinefunction(func)

            # Key Gen Helper
            def make_key(args, kwargs):
                from .utils import KeyGen

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
                if cached is not None:
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
                if cached is not None:
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

        # ケース1: @project.task として呼ばれた場合
        # _func にデコレート対象の関数が入ってくる
        if _func is not None and callable(_func):
            return decorator(_func)

        # ケース2: @project.task(save_blob=True) として呼ばれた場合
        # _func は None になり、decorator自体を返す（その後Pythonがfuncを入れて呼んでくれる）
        return decorator

