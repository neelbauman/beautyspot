# tests/unit/test_db_writer_queue.py

import sqlite3
import threading
import time
import pytest
from typing import Any
from beautyspot import Spot
from beautyspot.db import SQLiteTaskDB, TaskDBBase
from beautyspot.storage import LocalStorage


class FailingDB(TaskDBBase):
    def init_schema(self):
        pass

    def get(self, cache_key: str, *, include_expired: bool = False):
        return None

    def save(
        self,
        cache_key: str,
        func_name: str,
        func_identifier: str | None,
        input_id: str,
        version: str | None,
        result_type: str,
        content_type: str | None,
        result_value: str | None = None,
        result_data: bytes | None = None,
        expires_at=None,
    ):
        raise RuntimeError("db save failed")

    def get_history(self, limit: int = 1000) -> Any:
        return []

    def delete(self, cache_key: str) -> bool:
        return False


def test_save_failure_raises_sync_even_with_callback(tmp_path):
    """save_sync=True の場合、on_background_error が設定されていても例外が伝播する。"""
    errors: list[Exception] = []

    def on_error(err, _ctx):
        errors.append(err)

    spot = Spot(
        name="save_fail_sync",
        db=FailingDB(),
        storage_backend=LocalStorage(tmp_path / "blobs"),
        on_background_error=on_error,
    )

    @spot.mark
    def add_one(x):
        return x + 1

    with pytest.raises(RuntimeError, match="db save failed"):
        add_one(1)
    # コールバックも呼ばれていること
    assert errors
    assert isinstance(errors[0], RuntimeError)


@pytest.mark.asyncio
async def test_save_failure_raises_async_even_with_callback(tmp_path):
    """save_sync=True の場合、async関数でもon_background_error設定時に例外が伝播する。"""
    errors: list[Exception] = []

    def on_error(err, _ctx):
        errors.append(err)

    spot = Spot(
        name="save_fail_async",
        db=FailingDB(),
        storage_backend=LocalStorage(tmp_path / "blobs"),
        on_background_error=on_error,
    )

    @spot.mark
    async def add_one_async(x):
        return x + 1

    with pytest.raises(RuntimeError, match="db save failed"):
        await add_one_async(1)
    # コールバックも呼ばれていること
    assert errors
    assert isinstance(errors[0], RuntimeError)

    spot.shutdown(save_sync=True)


def test_sqlite_shutdown_waits_for_queue(tmp_path):
    db = SQLiteTaskDB(tmp_path / "test.db")
    db.init_schema()

    gate = threading.Event()
    write_done = threading.Event()
    shutdown_done = threading.Event()

    def slow_write():
        def op(conn: sqlite3.Connection):
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks
                (cache_key, func_name, input_id, version, result_type, content_type, result_value, result_data, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "key1",
                    "func",
                    "input",
                    None,
                    "DIRECT_BLOB",
                    None,
                    None,
                    b"x",
                    None,
                ),
            )
            gate.wait(timeout=2)

        db._enqueue_write(op)
        write_done.set()

    writer_thread = threading.Thread(target=slow_write)
    writer_thread.start()

    for _ in range(100):
        if db._write_queue.unfinished_tasks > 0:
            break
        time.sleep(0.01)
    else:
        gate.set()
        writer_thread.join(timeout=2)
        pytest.fail("write task did not enqueue")

    def do_shutdown():
        db.shutdown(wait=True)
        shutdown_done.set()

    shutdown_thread = threading.Thread(target=do_shutdown)
    shutdown_thread.start()

    time.sleep(0.05)
    assert not shutdown_done.is_set()

    gate.set()
    writer_thread.join(timeout=2)
    shutdown_thread.join(timeout=2)

    assert write_done.is_set()
    assert shutdown_done.is_set()

    with sqlite3.connect(db.db_path) as conn:
        row = conn.execute(
            "SELECT result_type, result_data FROM tasks WHERE cache_key=?",
            ("key1",),
        ).fetchone()
        assert row is not None
        assert row[0] == "DIRECT_BLOB"


def test_db_flush_waits_for_pending_writes(tmp_path):
    """
    flush() が、キューに積まれた重いタスクの完了を正しく待機することを検証する。
    """
    db = SQLiteTaskDB(tmp_path / "test.db")
    db.init_schema()

    # 意図的に時間がかかる書き込みタスクを投入
    def _slow_op(conn):
        time.sleep(0.5)

    # 内部の _enqueue_write は完了を同期で待つため、今回はキューに直接タスクを入れます
    from beautyspot.db import _WriteTask
    import threading

    task = _WriteTask(fn=_slow_op, event=threading.Event())
    db._write_queue.put(task)

    start = time.monotonic()
    # flush() は遅いタスクが終わるのを待つはず
    success = db.flush(timeout=2.0)
    elapsed = time.monotonic() - start

    assert success is True
    assert elapsed >= 0.5  # 少なくとも遅延させた分は待っていること


def test_db_flush_timeout(tmp_path):
    """
    flush() がタイムアウト時に False を返し、ブロックを解除することを検証する。
    """
    db = SQLiteTaskDB(tmp_path / "test.db")
    db.init_schema()

    def _very_slow_op(conn):
        time.sleep(2.0)

    from beautyspot.db import _WriteTask
    import threading

    task = _WriteTask(fn=_very_slow_op, event=threading.Event())
    db._write_queue.put(task)

    start = time.monotonic()
    # 短いタイムアウトで flush
    success = db.flush(timeout=0.2)
    elapsed = time.monotonic() - start

    assert success is False
    assert elapsed < 1.0  # タイムアウトですぐに抜けていること
