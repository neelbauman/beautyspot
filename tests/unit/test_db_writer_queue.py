# tests/unit/test_db_writer_queue.py

import sqlite3
import threading
import time

import pytest

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
        input_id: str,
        version: str | None,
        result_type: str,
        content_type: str | None,
        result_value: str | None = None,
        result_data: bytes | None = None,
        expires_at=None,
    ):
        raise RuntimeError("db save failed")

    def get_history(self, limit: int = 1000):
        return []

    def delete(self, cache_key: str) -> bool:
        return False


def test_save_failure_does_not_raise_sync(tmp_path):
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

    assert add_one(1) == 2
    assert errors
    assert isinstance(errors[0], RuntimeError)


@pytest.mark.asyncio
async def test_save_failure_does_not_raise_async(tmp_path):
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

    assert await add_one_async(1) == 2
    assert errors
    assert isinstance(errors[0], RuntimeError)

    spot.shutdown(wait=True)


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
