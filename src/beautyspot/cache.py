# src/beautyspot/cache.py

import hashlib
import logging
import threading
import time
import asyncio
import contextlib
from datetime import datetime, timezone
from typing import Any, Callable, Optional, NamedTuple, Generator, AsyncGenerator

from beautyspot.db import TaskDBMaintenable
from beautyspot.storage import BlobStorageMaintenable, StoragePolicyProtocol
from beautyspot.serializer import SerializerProtocol
from beautyspot.lifecycle import (
    LifecyclePolicy,
    RetentionSpec,
    parse_retention,
    _ForeverSentinel,
    _FOREVER,
)
from beautyspot.cachekey import KeyGen
from beautyspot.exceptions import CacheCorruptedError
from beautyspot.content_types import ContentType

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# --- キャッシュミスを表す番兵オブジェクト ---
CACHE_MISS = object()


class HerdWaitResult(NamedTuple):
    """Thundering Herd 待機フェーズの結果。"""

    is_executor: bool  # True: 自分が実行者になった
    result: Any  # is_executor=False のときの結果 or 例外
    event: threading.Event | None  # is_executor=True のときのイベント
    result_box: list  # is_executor=True のときの共有リスト
    is_error: bool  # result が例外の場合 True


class CacheManager:
    """
    キャッシュの読み書き、キー生成、および並行実行制御（Thundering Herd対策）を
    担当するコンポーネント。
    """

    HERD_POLL: float = 5.0
    HERD_TIMEOUT: float = 300.0
    HERD_MAX_RETRIES: int = 3

    def __init__(
        self,
        db: TaskDBMaintenable,
        storage: BlobStorageMaintenable,
        serializer: SerializerProtocol,
        storage_policy: StoragePolicyProtocol,
        lifecycle_policy: Optional[LifecyclePolicy] = None,
    ):
        self.db = db
        self.storage = storage
        self.serializer = serializer
        self.storage_policy = storage_policy

        if lifecycle_policy is not None:
            self.lifecycle_policy = lifecycle_policy
        else:
            self.lifecycle_policy = LifecyclePolicy.default()

        # サンダリングハード対策: 同一キーの並行実行を直列化する
        # tuple: (threading.Event, list[asyncio.Future], list[result])
        self._inflight: dict[
            str, tuple[threading.Event, list[asyncio.Future], list]
        ] = {}
        self._inflight_lock = threading.Lock()

    def make_cache_key(
        self,
        func_identifier: str,
        args: tuple,
        kwargs: dict,
        resolved_key_fn: Optional[Callable],
        version: str | None,
    ) -> tuple[str, str]:
        """キャッシュキーと入力IDを生成する。"""
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

    def calculate_expires_at(
        self,
        func_identifier: str,
        func_name: str,
        local_retention: RetentionSpec,
    ) -> Optional[datetime]:
        """有効期限を計算する。"""
        if local_retention is _FOREVER:
            return None

        if isinstance(local_retention, _ForeverSentinel):
            raise RuntimeError(
                "Internal Error: _ForeverSentinel reached calculate_expires_at."
            )

        retention = parse_retention(local_retention)

        if retention is None:
            retention = self.lifecycle_policy.resolve_with_fallback(
                func_identifier, func_name
            )

        if retention is None:
            return None

        return datetime.now(timezone.utc) + retention

    def get(
        self, cache_key: str, serializer: Optional[SerializerProtocol] = None
    ) -> Any:
        """同期的にキャッシュから値を取得する。"""
        use_serializer = serializer or self.serializer
        entry = self.db.get(cache_key)

        if not entry:
            return CACHE_MISS

        r_type = entry["result_type"]
        r_val = entry["result_value"]
        r_data = entry.get("result_data")

        try:
            if r_type == "DIRECT_BLOB":
                if r_data is None:
                    return CACHE_MISS
                return use_serializer.loads(r_data)

            elif r_type == "FILE":
                if r_val is None:
                    logger.warning(
                        f"Data corruption: 'FILE' record has no path for key `{cache_key}`"
                    )
                    return CACHE_MISS
                data_bytes = self.storage.load(r_val)
                return use_serializer.loads(data_bytes)

            else:
                logger.warning(
                    f"Unknown result_type '{r_type}' for cache_key `{cache_key}`"
                )
                return CACHE_MISS

        except CacheCorruptedError as e:
            logger.debug(f"Cache corrupted for {cache_key}: {e}")
            return CACHE_MISS
        except Exception as e:
            logger.error(
                f"Failed to deserialize cache for `{cache_key}`: {e}", exc_info=True
            )
            return CACHE_MISS

    def set(
        self,
        cache_key: str,
        func_name: str,
        func_identifier: str,
        input_id: str,
        version: str | None,
        result: Any,
        content_type: str | ContentType | None,
        save_blob: bool | None,
        expires_at: Optional[datetime] = None,
        serializer: Optional[SerializerProtocol] = None,
    ) -> None:
        """同期的にキャッシュへ値を保存する。"""
        use_serializer = serializer or self.serializer
        data_bytes = use_serializer.dumps(result)

        should_use_blob = save_blob
        if should_use_blob is None:
            should_use_blob = self.storage_policy.should_save_as_blob(data_bytes)

        if should_use_blob:
            r_val = self.storage.save(cache_key, data_bytes)
            try:
                self.db.save(
                    cache_key=cache_key,
                    func_name=func_name,
                    func_identifier=func_identifier,
                    input_id=input_id,
                    version=version,
                    result_type="FILE",
                    content_type=content_type,
                    result_value=r_val,
                    result_data=None,
                    expires_at=expires_at,
                )
            except Exception:
                try:
                    self.storage.delete(r_val)
                except Exception as rollback_err:
                    logger.warning(f"Failed to rollback blob '{r_val}': {rollback_err}")
                raise
        else:
            self.db.save(
                cache_key=cache_key,
                func_name=func_name,
                func_identifier=func_identifier,
                input_id=input_id,
                version=version,
                result_type="DIRECT_BLOB",
                content_type=content_type,
                result_value=None,
                result_data=data_bytes,
                expires_at=expires_at,
            )

    # --- Thundering Herd Protection ---

    @contextlib.contextmanager
    def herd_sync(
        self, cache_key: str, serializer: Optional[SerializerProtocol] = None
    ) -> Generator[HerdWaitResult, None, None]:
        """同期パスでの Thundering Herd 保護コンテキストマネージャ。"""
        herd = self.wait_herd_sync(cache_key, serializer)
        try:
            yield herd
        finally:
            if herd.is_executor:
                self.notify_and_cleanup_inflight(cache_key, herd.event, herd.result_box)

    @contextlib.asynccontextmanager
    async def herd_async(
        self,
        cache_key: str,
        serializer: Optional[SerializerProtocol],
        loop: asyncio.AbstractEventLoop,
        executor: Any,
    ) -> AsyncGenerator[HerdWaitResult, None]:
        """非同期パスでの Thundering Herd 保護コンテキストマネージャ。"""
        herd = await self.wait_herd_async(cache_key, serializer, loop, executor)
        try:
            yield herd
        finally:
            if herd.is_executor:
                self.notify_and_cleanup_inflight(cache_key, herd.event, herd.result_box)

    def wait_herd_sync(
        self, cache_key: str, serializer: Optional[SerializerProtocol] = None
    ) -> HerdWaitResult:
        """同期パスでの Thundering Herd 待機。"""
        retries = 0
        while True:
            with self._inflight_lock:
                if cache_key not in self._inflight:
                    event = threading.Event()
                    result_box: list = []
                    self._inflight[cache_key] = (event, [], result_box)
                    return HerdWaitResult(True, None, event, result_box, False)

                wait_event, _, wait_box = self._inflight[cache_key]

            deadline = time.monotonic() + self.HERD_TIMEOUT
            while not wait_event.wait(timeout=self.HERD_POLL):
                if time.monotonic() >= deadline:
                    retries += 1
                    if retries > self.HERD_MAX_RETRIES:
                        raise TimeoutError(f"Herd wait timeout for {cache_key} exceeded max retries ({self.HERD_MAX_RETRIES})")
                    logger.warning(f"Herd wait timeout for {cache_key} (retry {retries}/{self.HERD_MAX_RETRIES})")
                    break

            if wait_box:
                success, val = wait_box[0]
                return HerdWaitResult(False, val, None, [], not success)

            # 万が一の結果漏れに備えて再チェック
            cached = self.get(cache_key, serializer)
            if cached is not CACHE_MISS:
                return HerdWaitResult(False, cached, None, [], False)

    async def wait_herd_async(
        self,
        cache_key: str,
        serializer: Optional[SerializerProtocol],
        loop: asyncio.AbstractEventLoop,
        executor: Any,
    ) -> HerdWaitResult:
        """非同期パスでの Thundering Herd 待機。"""
        retries = 0
        while True:
            fut = None
            with self._inflight_lock:
                if cache_key not in self._inflight:
                    event = threading.Event()
                    result_box: list = []
                    self._inflight[cache_key] = (event, [], result_box)
                    return HerdWaitResult(True, None, event, result_box, False)

                wait_event, futs, wait_box = self._inflight[cache_key]
                if not wait_box:
                    fut = loop.create_future()
                    futs.append(fut)

            signal = await self._await_herd_signal_async(
                fut, wait_event, wait_box, cache_key, loop, executor
            )
            if signal is None:
                retries += 1
                if retries > self.HERD_MAX_RETRIES:
                    raise TimeoutError(f"Herd wait timeout for {cache_key} exceeded max retries ({self.HERD_MAX_RETRIES})")
                logger.warning(f"Herd wait timeout for {cache_key} (retry {retries}/{self.HERD_MAX_RETRIES})")
                continue

            success, val = signal
            return HerdWaitResult(False, val, None, [], not success)

    async def _await_herd_signal_async(
        self,
        fut: Optional[asyncio.Future],
        wait_event: threading.Event,
        wait_box: list,
        cache_key: str,
        loop: asyncio.AbstractEventLoop,
        executor: Any,
    ) -> Optional[tuple[bool, Any]]:
        if fut is not None:
            try:
                val = await asyncio.wait_for(
                    asyncio.shield(fut), timeout=self.HERD_TIMEOUT
                )
                return (True, val)
            except asyncio.TimeoutError:
                return None
            except Exception as e:
                return (False, e)

        if wait_box:
            return wait_box[0]

        deadline = time.monotonic() + self.HERD_TIMEOUT
        while not await loop.run_in_executor(executor, wait_event.wait, self.HERD_POLL):
            if time.monotonic() >= deadline:
                return None

        return wait_box[0] if wait_box else None

    def notify_and_cleanup_inflight(
        self,
        cache_key: str,
        event: Optional[threading.Event],
        result_box: list,
    ) -> None:
        """待機中のスレッド/タスクに通知し、管理情報を削除する。"""
        futs_to_notify: list = []
        with self._inflight_lock:
            val = self._inflight.get(cache_key)
            if val is not None and val[0] is event:
                _, futs_to_notify, _ = val
                del self._inflight[cache_key]

        if event is not None:
            event.set()
            if result_box and futs_to_notify:
                success, res_val = result_box[0]
                for fut in futs_to_notify:
                    if not fut.done():
                        self._notify_future(fut, success, res_val)

    def _notify_future(self, fut: asyncio.Future, success: bool, val: Any) -> None:
        def _set():
            if not fut.done():
                if success:
                    fut.set_result(val)
                elif isinstance(val, BaseException):
                    fut.set_exception(val)
                else:
                    fut.set_exception(RuntimeError(f"Non-Exception error: {repr(val)}"))

        fut.get_loop().call_soon_threadsafe(_set)
