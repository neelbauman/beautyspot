# tests/integration/core/test_background_loop.py

"""asyncio バックグラウンドループによる保存の統合テスト。"""

import time
from unittest.mock import MagicMock

import beautyspot as bs
from beautyspot.db import SQLiteTaskDB


def test_background_loop_saves_correctly(tmp_path):
    """_BackgroundLoop 経由の wait=False 保存が正しく動作することを確認する。"""
    db_path = tmp_path / "bg.db"
    spot = bs.Spot(
        name="bg_test",
        db=SQLiteTaskDB(db_path),
        storage_backend=bs.LocalStorage(tmp_path / "blobs"),
        default_wait=False,
    )

    @spot.mark()
    def add(x, y):
        return x + y

    with spot:
        result = add(3, 4)
        assert result == 7

    # __exit__ でドレイン完了後、DB にレコードが存在することを確認
    rows = spot.db.get_history()
    assert len(rows) == 1
    assert rows.iloc[0]["func_name"] == "add"


def test_background_loop_serializes_saves(tmp_path):
    """wait=False で複数タスクを投入しても、保存が直列化されることを確認する。"""
    db_path = tmp_path / "serial.db"
    spot = bs.Spot(
        name="serial_test",
        db=SQLiteTaskDB(db_path),
        storage_backend=bs.LocalStorage(tmp_path / "blobs"),
        default_wait=False,
    )

    @spot.mark()
    def identity(x):
        return x

    with spot:
        for i in range(5):
            identity(i)

    # 全レコードが保存されていること
    rows = spot.db.get_history()
    assert len(rows) == 5


def test_background_loop_with_blob_storage(tmp_path):
    """wait=False + blob ストレージでも正しく保存されることを確認する。"""
    db_path = tmp_path / "blob.db"
    blob_dir = tmp_path / "blobs"
    spot = bs.Spot(
        name="blob_test",
        db=SQLiteTaskDB(db_path),
        storage_backend=bs.LocalStorage(blob_dir),
        default_wait=False,
        default_save_blob=True,
    )

    @spot.mark()
    def make_data(n):
        return list(range(n))

    with spot:
        result = make_data(100)
        assert result == list(range(100))

    rows = spot.db.get_history()
    assert len(rows) == 1
    assert rows.iloc[0]["result_type"] == "FILE"


def test_background_loop_fires_error_callback(tmp_path, mocker):
    """バックグラウンド保存失敗時に on_background_error が呼ばれることを確認する。"""
    mock_callback = MagicMock()
    spot = bs.Spot(
        name="err_test",
        db=MagicMock(),
        serializer=MagicMock(),
        storage_backend=MagicMock(),
        storage_policy=MagicMock(),
        limiter=MagicMock(),
        default_wait=False,
        on_background_error=mock_callback,
    )

    test_exc = RuntimeError("disk full")
    mocker.patch.object(spot, "_save_result_sync", side_effect=test_exc)

    @spot.mark()
    def task(x):
        return x * 2

    result = task(5)
    spot.shutdown(wait=True)

    assert result == 10
    mock_callback.assert_called_once()
    passed_exc, ctx = mock_callback.call_args[0]
    assert passed_exc is test_exc
    assert ctx.func_name == "task"


def test_shutdown_after_background_saves(tmp_path):
    """shutdown(wait=True) が保留中のバックグラウンド保存を待つことを確認する。"""
    slow_storage = MagicMock()

    def slow_save(key, data):
        time.sleep(0.5)
        return "mock_loc"

    slow_storage.save.side_effect = slow_save

    spot = bs.Spot(
        name="shutdown_test",
        db=SQLiteTaskDB(tmp_path / "s.db"),
        storage_backend=slow_storage,
        default_wait=False,
        default_save_blob=True,
    )

    @spot.mark()
    def fn(x):
        return x

    fn(42)

    start = time.time()
    spot.shutdown(wait=True)
    elapsed = time.time() - start

    assert elapsed >= 0.4, "shutdown should wait for pending saves"
