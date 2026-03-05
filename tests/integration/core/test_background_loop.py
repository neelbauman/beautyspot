# tests/integration/core/test_background_loop.py

"""asyncio バックグラウンドループによる保存の統合テスト。"""

import time
import threading
import beautyspot as bs
import asyncio
import pytest
from unittest.mock import MagicMock
from beautyspot.core import _BackgroundLoop
from beautyspot.db import SQLiteTaskDB


def test_background_loop_saves_correctly(tmp_path):
    """_BackgroundLoop 経由の save_sync=False 保存が正しく動作することを確認する。"""
    db_path = tmp_path / "bg.db"
    spot = bs.Spot(
        name="bg_test",
        db=SQLiteTaskDB(db_path),
        storage_backend=bs.LocalStorage(tmp_path / "blobs"),
        save_sync=False,
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
    """save_sync=False で複数タスクを投入しても、保存が直列化されることを確認する。"""
    db_path = tmp_path / "serial.db"
    spot = bs.Spot(
        name="serial_test",
        db=SQLiteTaskDB(db_path),
        storage_backend=bs.LocalStorage(tmp_path / "blobs"),
        save_sync=False,
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
    """save_sync=False + blob ストレージでも正しく保存されることを確認する。"""
    db_path = tmp_path / "blob.db"
    blob_dir = tmp_path / "blobs"
    spot = bs.Spot(
        name="blob_test",
        db=SQLiteTaskDB(db_path),
        storage_backend=bs.LocalStorage(blob_dir),
        save_sync=False,
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
        save_sync=False,
        on_background_error=mock_callback,
    )

    test_exc = RuntimeError("disk full")
    mocker.patch.object(spot.cache, "set", side_effect=test_exc)

    @spot.mark()
    def task(x):
        return x * 2

    result = task(5)
    spot.shutdown(save_sync=True)

    assert result == 10
    mock_callback.assert_called_once()
    passed_exc, ctx = mock_callback.call_args[0]
    assert passed_exc is test_exc
    assert ctx.func_name == "task"


def test_shutdown_after_background_saves(tmp_path):
    """shutdown(save_sync=True) が保留中のバックグラウンド保存を待つことを確認する。"""
    slow_storage = MagicMock()

    def slow_save(key, data):
        time.sleep(0.5)
        return "mock_loc"

    slow_storage.save.side_effect = slow_save

    spot = bs.Spot(
        name="shutdown_test",
        db=SQLiteTaskDB(tmp_path / "s.db"),
        storage_backend=slow_storage,
        save_sync=False,
        default_save_blob=True,
    )

    @spot.mark()
    def fn(x):
        return x

    fn(42)

    start = time.time()
    spot.shutdown(save_sync=True)
    elapsed = time.time() - start

    assert elapsed >= 0.4, "shutdown should wait for pending saves"


def test_background_loop_basic_submit_and_drain():
    """
    正常系: タスクを投入し、stop(save_sync=True) で全てのタスクが確実に完了（ドレイン）することを確認する。
    """
    loop = _BackgroundLoop(drain_timeout=2.0)
    results = []

    async def sample_task(task_id: int):
        await asyncio.sleep(0.1)
        results.append(task_id)

    # 3つのタスクを投入
    f1 = loop.submit(sample_task(1))
    f2 = loop.submit(sample_task(2))
    f3 = loop.submit(sample_task(3))

    assert f1 is not None and f2 is not None and f3 is not None

    # シャットダウン開始（全てのタスクの完了を待機するはず）
    loop.stop(save_sync=True)

    # 全てのタスクが処理されていること
    assert sorted(results) == [1, 2, 3]
    # スレッドが正しく終了していること
    assert not loop._thread.is_alive()


def test_background_loop_rejects_tasks_after_stop():
    """
    エッジケース: シャットダウンシーケンスに入った後は、新規タスクの投入が拒否（Noneが返却）されること。
    """
    loop = _BackgroundLoop(drain_timeout=1.0)

    # 停止
    loop.stop(save_sync=True)

    async def dummy_task():
        pass

    # 停止後の投入は None を返すはず
    coro = dummy_task()
    future = loop.submit(coro)
    assert future is None
    # 拒否時にコルーチンが close されること（未await警告対策）
    assert coro.cr_frame is None


def test_background_loop_handles_task_exceptions():
    """
    異常系: バックグラウンドタスク内で例外が発生しても、ループ自体はクラッシュせず、
    Future経由で正しく例外を捕捉できること。
    """
    loop = _BackgroundLoop(drain_timeout=1.0)

    async def failing_task():
        await asyncio.sleep(0.05)
        raise ValueError("Something went wrong in background")

    async def successful_task():
        await asyncio.sleep(0.1)
        return "Success"

    # 失敗するタスクと成功するタスクを両方投入
    future_fail = loop.submit(failing_task())
    future_succ = loop.submit(successful_task())

    assert future_fail is not None
    assert future_succ is not None

    # failing_task の例外を Future から捕捉
    with pytest.raises(ValueError, match="Something went wrong in background"):
        future_fail.result(timeout=1.0)

    # successful_task は巻き添えにならず正常に完了する
    assert future_succ.result(timeout=1.0) == "Success"

    loop.stop(save_sync=True)


def test_background_loop_stop_no_wait():
    """
    GCファイナライザ用: stop(save_sync=False) が呼ばれた場合、
    メインスレッドをブロックせずに即座に制御を返すこと。
    """
    loop = _BackgroundLoop(drain_timeout=5.0)

    task_started = threading.Event()

    async def slow_task():
        task_started.set()
        await asyncio.sleep(2.0)  # 意図的に遅いタスク

    loop.submit(slow_task())

    # タスクの開始を待つ
    assert task_started.wait(timeout=1.0)

    start_time = time.time()
    # wait=False なので、タスクの完了を待たずに即座にリターンするはず
    loop.stop(save_sync=False)
    elapsed = time.time() - start_time

    assert elapsed < 0.5  # 2秒待たずにすぐ返ってきていること
