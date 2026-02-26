# tests/integration/core/test_thundering_herd_exception.py
"""SPEC-012: Thundering Herd の同期関数における例外伝播テスト"""

import asyncio
import threading
import time

import pytest
import beautyspot as bs
from beautyspot.db import SQLiteTaskDB


@pytest.mark.asyncio
async def test_thundering_herd_sync_exception_propagation(tmp_path):
    """同期関数の例外が全待機スレッドに伝播すること"""
    db_path = tmp_path / "test.db"
    spot = bs.Spot("test_herd_exc", db=SQLiteTaskDB(db_path), save_sync=True)

    class TaskError(Exception):
        pass

    call_count = 0
    lock = threading.Lock()

    @spot.mark
    def failing_task(x):
        nonlocal call_count
        with lock:
            call_count += 1
        time.sleep(0.5)
        raise TaskError("sync failure")

    exceptions = [None] * 5

    loop = asyncio.get_running_loop()

    def worker(idx):
        try:
            failing_task(42)
        except TaskError as e:
            exceptions[idx] = e

    await asyncio.gather(
        *(loop.run_in_executor(None, worker, i) for i in range(5))
    )

    # 関数は1回だけ実行される
    assert call_count == 1

    # 全スレッドに同じ例外が伝播する
    for i in range(5):
        assert exceptions[i] is not None, f"Thread {i} did not receive exception"
        assert isinstance(exceptions[i], TaskError)
        assert str(exceptions[i]) == "sync failure"
