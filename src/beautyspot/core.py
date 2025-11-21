# src/beautyspot/core.py

import sqlite3
import json
import hashlib
import os
import functools
import inspect
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional, Union

from .limiter import TokenBucket
from .storage import LocalStorage, S3Storage

# グローバルIO用スレッドプール
_io_executor = ThreadPoolExecutor(max_workers=4)

class Project:
    def __init__(self, name: str, db_path: str | None = None, storage_path: str = "./blobs", s3_opts: dict | None = None, tpm: int = 10000):
        
        self.name = name
        self.db_path = db_path or f"{name}.db"
        self.bucket = TokenBucket(tpm)
        
        # Storage Selection
        if storage_path.startswith("s3://"):
            self.storage = S3Storage(storage_path, s3_opts)
        else:
            self.storage = LocalStorage(storage_path)
            
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    cache_key TEXT PRIMARY KEY,
                    func_name TEXT,
                    input_id  TEXT,
                    result_type TEXT,
                    result_value TEXT, 
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    # --- Core Logic (Sync) ---
    def _check_cache_sync(self, cache_key: str) -> Any:
        """戻り値が None ならキャッシュミス"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT result_type, result_value FROM tasks WHERE cache_key=?", (cache_key,)).fetchone()
            if row:
                r_type, r_val = row
                if r_type == 'DIRECT':
                    return json.loads(r_val)
                elif r_type == 'FILE':
                    try:
                        return self.storage.load(r_val)
                    except FileNotFoundError:
                        return None
        return None

    def _save_result_sync(self, cache_key: str, func_name: str, input_id: str, result: Any, save_blob: bool):
        if save_blob:
            r_val = self.storage.save(cache_key, result)
            r_type = 'FILE'
        else:
            r_type = 'DIRECT'
            r_val = json.dumps(result, default=str)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tasks (cache_key, func_name, input_id, result_type, result_value) VALUES (?, ?, ?, ?, ?)",
                (cache_key, func_name, input_id, r_type, r_val)
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

    def task(self, _func: Optional[Callable] = None, *, save_blob: bool = False, input_key_fn: Optional[Callable] = None):
        """
        Resumable Task Decorator
        Supports both @project.task and @project.task(save_blob=True)
        """
        def decorator(func):
            is_async = inspect.iscoroutinefunction(func)
            
            # Key Gen Helper
            def make_key(args, kwargs):
                from .utils import KeyGen
                iid = input_key_fn(*args, **kwargs) if input_key_fn else KeyGen.default(args, kwargs)
                ck = hashlib.md5(f"{func.__name__}:{iid}".encode()).hexdigest()
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
                self._save_result_sync(ck, func.__name__, str(iid), res, save_blob)
                return res

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                iid, ck = make_key(args, kwargs)
                loop = asyncio.get_running_loop()

                # 1. Check Cache (Offload IO)
                cached = await loop.run_in_executor(_io_executor, self._check_cache_sync, ck)
                if cached is not None: return cached

                # 2. Execute (Async)
                res = await func(*args, **kwargs)

                # 3. Save (Offload IO)
                await loop.run_in_executor(_io_executor, self._save_result_sync, ck, func.__name__, str(iid), res, save_blob)
                return res

            return async_wrapper if is_async else sync_wrapper

        # --- 修正ポイント: 呼び出し方の判定ロジック ---
        
        # ケース1: @project.task として呼ばれた場合
        # _func にデコレート対象の関数が入ってくる
        if _func is not None and callable(_func):
            return decorator(_func)
            
        # ケース2: @project.task(save_blob=True) として呼ばれた場合
        # _func は None になり、decorator自体を返す（その後Pythonがfuncを入れて呼んでくれる）
        return decorator
