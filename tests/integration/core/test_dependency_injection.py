# tests/integration/core/test_dependency_injection.py

from concurrent.futures import ThreadPoolExecutor
import msgpack
import pytest
from typing import Iterator
from beautyspot import Spot
from beautyspot.storage import BlobStorageBase, LocalStorage, ReadableBuffer
from beautyspot.db import TaskDBBase, SQLiteTaskDB


class MockStorage(BlobStorageBase):
    def __init__(self):
        self.data = {}

    def save(self, key: str, data: ReadableBuffer) -> str:
        self.data[key] = bytes(data)
        return f"mock://{key}"

    def load(self, location: str) -> bytes:
        key = location.replace("mock://", "")
        if key not in self.data:
            raise FileNotFoundError(key)
        return self.data[key]

    def delete(self, location: str) -> None:
        key = location.replace("mock://", "")
        if key in self.data:
            del self.data[key]

    def list_keys(self) -> Iterator[str]:
        """
        Yields location identifiers (mock://...) for all stored data.
        Required by BlobStorageBase interface.
        """
        for key in self.data:
            yield f"mock://{key}"


class MockDB(TaskDBBase):
    def __init__(self):
        self.store = {}

    def init_schema(self):
        pass

    def get(self, cache_key: str, *, include_expired: bool = False):
        return self.store.get(cache_key)

    def save(
        self,
        cache_key,
        func_name,
        func_identifier,
        input_id,
        version,
        result_type,
        content_type,
        result_value=None,
        result_data=None,
        expires_at=None,
    ):
        self.store[cache_key] = {
            "func_name": func_name,
            "result_value": result_value,
            "result_data": result_data,
            "result_type": result_type,
        }

    def delete(self, cache_key: str) -> bool:
        if cache_key in self.store:
            del self.store[cache_key]
            return True
        return False

    def get_history(self, limit=1000):
        import pandas as pd

        return pd.DataFrame(list(self.store.values()))


def test_custom_storage_injection(tmp_path):
    """Test injecting a custom storage backend."""
    storage = MockStorage()
    project = Spot(
        name="di_test",
        db=SQLiteTaskDB(str(tmp_path / "test.db")),
        storage_backend=storage,
    )

    @project.mark(save_blob=True)
    def blob_task():
        return "blob_data"

    res = blob_task()
    assert res == "blob_data"

    # Verify data ended up in our mock storage
    assert len(storage.data) == 1
    # Key is md5 hash, so we just check if any key exists
    key = list(storage.data.keys())[0]
    assert (
        b"blob_data" in storage.data[key]
    )  # msgpack serialized string might contain the string itself


def test_custom_db_injection(tmp_path):
    """Test injecting a custom DB backend."""

    db = MockDB()
    project = Spot(
        name="di_test", db=db, storage_backend=LocalStorage(tmp_path / "blobs")
    )

    @project.mark
    def simple_task():
        return 123

    res = simple_task()
    assert res == 123

    # Verify metadata ended up in our mock DB
    assert len(db.store) == 1
    key = list(db.store.keys())[0]

    # DIRECT_B64 ではなく DIRECT_BLOB を確認
    assert db.store[key]["result_type"] == "DIRECT_BLOB"

    # result_value (Base64) ではなく result_data (Bytes) を確認
    stored_bytes = db.store[key]["result_data"]
    assert msgpack.unpackb(stored_bytes) == 123


def test_custom_executor_injection(tmp_path):
    """Test injecting a custom executor (deprecated, but still functional)."""
    executor = ThreadPoolExecutor(max_workers=1)
    with pytest.warns(DeprecationWarning, match="executor.*deprecated"):
        project = Spot(
            name="di_test",
            db=SQLiteTaskDB(tmp_path / "test.db"),
            storage_backend=LocalStorage(str(tmp_path / "blobs")),
            executor=executor,
        )

    @project.mark
    def task_a():
        return "A"

    assert task_a() == "A"

    # Executor should remain open after project shutdown if injected?
    # The current implementation says:
    # if executor is not None: ... self._own_executor = False
    # so project.shutdown() should NOT shut it down.

    project.shutdown()

    # Verify executor is still usable
    f = executor.submit(lambda: "still_alive")
    assert f.result() == "still_alive"

    executor.shutdown()


def test_deprecated_executor_not_overwritten_by_ensure_bg_resources(tmp_path):
    """
    deprecated executor を渡した場合、_ensure_bg_resources() 呼び出し後も
    ユーザーの executor が保持されることを検証する。
    """
    user_executor = ThreadPoolExecutor(max_workers=1)
    with pytest.warns(DeprecationWarning, match="executor.*deprecated"):
        spot = Spot(
            name="di_test_ensure",
            db=SQLiteTaskDB(tmp_path / "test_ensure.db"),
            storage_backend=LocalStorage(str(tmp_path / "blobs_ensure")),
            executor=user_executor,
        )

    # executor が設定されていることを確認
    assert spot._executor is user_executor
    assert spot._bg_loop is None

    # _ensure_bg_resources を呼ぶ（async パスで呼ばれるケースをシミュレート）
    bg_loop, executor = spot._ensure_bg_resources()

    # _bg_loop が新たに生成されていること
    assert bg_loop is not None
    assert spot._bg_loop is bg_loop

    # ユーザーの executor が上書きされていないこと
    assert spot._executor is user_executor
    assert executor is user_executor

    # クリーンアップ
    bg_loop.stop(wait=True)
    user_executor.shutdown()


def test_deprecated_executor_shutdown_cleans_bg_loop(tmp_path):
    """
    shutdown() が _bg_loop を停止しつつ、
    ユーザーの executor は閉じないことを検証する。
    """
    user_executor = ThreadPoolExecutor(max_workers=1)
    with pytest.warns(DeprecationWarning, match="executor.*deprecated"):
        spot = Spot(
            name="di_test_shutdown",
            db=SQLiteTaskDB(tmp_path / "test_shutdown.db"),
            storage_backend=LocalStorage(str(tmp_path / "blobs_shutdown")),
            executor=user_executor,
        )

    # _ensure_bg_resources で _bg_loop を生成
    spot._ensure_bg_resources()
    assert spot._bg_loop is not None

    bg_loop = spot._bg_loop

    # shutdown 呼び出し
    spot.shutdown(wait=True)

    # _bg_loop は停止されていること
    assert bg_loop._is_shutting_down is True

    # ユーザーの executor はまだ使えること
    f = user_executor.submit(lambda: "alive")
    assert f.result() == "alive"

    user_executor.shutdown()
