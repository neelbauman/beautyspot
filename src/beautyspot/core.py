# src/beautyspot/core.py

import json
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
from .db import TaskDB
from .serializer import MsgpackSerializer, SerializationError

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

class Project:
    def __init__(
        self,
        name: str,
        db_path: str | None = None,
        storage_path: str = "./blobs",
        s3_opts: dict | None = None,
        tpm: int = 10000,
        io_workers: int = 4,
        executor: Optional[Executor] = None,
        storage: Optional[BlobStorageBase] = None,
    ):
        self.name = name
        self.db_path = db_path or f"{name}.db"
        self.bucket = TokenBucket(tpm)

        self.db = TaskDB(self.db_path)
        self.db.init_schema()

        self.serializer = MsgpackSerializer()
        
        # Storage Selection
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
            # selfへの強い参照を持たせないよう、executorオブジェクトだけを残す
            self._finalizer = weakref.finalize(self, self._shutdown_executor, self.executor)

    @staticmethod
    def _shutdown_executor(executor: Executor):
        """
        内部Executor用のクリーンアップ関数
        """
        executor.shutdown(wait=True)

    def shutdown(self, wait: bool = True):
        """
        手動でリソースを解放する場合に使用
        """
        if self._own_executor and self._finalizer.alive:
            self._finalizer()

    def register_type(self, type_: Type, code: int, encoder: Callable, decoder: Callable):
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
        """戻り値が None ならキャッシュミス"""
        entry = self.db.get(cache_key)

        if entry:
            r_type = entry["result_type"]
            r_val = entry["result_value"]
            if r_type == 'DIRECT':
                return json.loads(r_val)
            elif r_type == 'FILE':
                try:
                    data_bytes = self.storage.load(r_val)
                    return self.serializer.loads(data_bytes)
                except FileNotFoundError:
                    logger.warning(f"Cache blob missing for key {cache_key}. Re-computing.")
                    return None
                except (ValueError, SerializationError, Exception) as e:
                    logger.warning(
                        f"⚠️ Cache corrupted or incompatible for '{cache_key}'. Re-computing...\n"
                        f"   Error: {e}"
                    )
                    return None
                # except CacheCorruptedError as e:
                #     logger.warning(
                #         f"⚠️ Cache corrupted for '{cache_key}' (likely due to code changes). Re-computing...\n"
                #         f"   Error: {e}\n"
                #         f"   Hint: Consider updating 'version' in @task(version=...) to avoid unintended recalculation."
                #     )
                #     return None
        return None

    def _save_result_sync(self, cache_key: str, func_name: str, input_id: str, version: str | None, result: Any, content_type: str | None, save_blob: bool):
        if save_blob:
            data_bytes = self.serializer.dumps(result)
            r_val = self.storage.save(cache_key, data_bytes)
            r_type = 'FILE'
        else:
            # Small data: Keep using JSON for now to maintain DB readability
            # Note: This limits `save_blob=False` to JSON-serializable types only.
            # If users want to use Custom Types, they should prefer `save_blob=True` 
            # OR we can switch this to base64 encoded msgpack in the future.
            r_type = 'DIRECT'
            r_val = json.dumps(result, default=str)

        self.db.save(
            cache_key=cache_key,
            func_name=func_name,
            input_id=input_id,
            version=version,
            result_type=r_type,
            content_type=content_type,
            result_value=r_val,
        )

    # --- Decorators ---

    def limiter(self, cost: Union[int, Callable] = 1):
        """Rate Limiting Decorator"""
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
                iid = input_key_fn(*args, **kwargs) if input_key_fn else KeyGen.default(args, kwargs)
                
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
                if cached is not None: return cached

                # 2. Execute
                res = func(*args, **kwargs)

                # 3. Save
                self._save_result_sync(ck, func.__name__, str(iid), version, res, content_type, save_blob)
                return res

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                iid, ck = make_key(args, kwargs)
                loop = asyncio.get_running_loop()

                # 1. Check Cache (Offload IO)
                cached = await loop.run_in_executor(self.executor, self._check_cache_sync, ck)
                if cached is not None: return cached

                # 2. Execute (Async)
                res = await func(*args, **kwargs)

                # 3. Save (Offload IO)
                await loop.run_in_executor(self.executor, self._save_result_sync, ck, func.__name__, str(iid), version, res, content_type, save_blob)
                return res

            return async_wrapper if is_async else sync_wrapper

        # ケース1: @project.task として呼ばれた場合
        # _func にデコレート対象の関数が入ってくる
        if _func is not None and callable(_func):
            return decorator(_func)
            
        # ケース2: @project.task(save_blob=True) として呼ばれた場合
        # _func は None になり、decorator自体を返す（その後Pythonがfuncを入れて呼んでくれる）
        return decorator

