import time
import pytest
from unittest.mock import MagicMock
from beautyspot import Spot
from beautyspot.db import SQLiteTaskDB


@pytest.fixture
def spot_with_slow_storage(tmp_path):
    """保存が0.5秒かかる低速ストレージを持つSpotを作成するフィクスチャ"""
    db_path = tmp_path / "test.db"

    # Storageのsaveメソッドをモックし、0.5秒待機させる
    slow_storage = MagicMock()

    def slow_save(key, data):
        time.sleep(0.5)
        return f"path/{key}"

    slow_storage.save.side_effect = slow_save

    # default_wait=False (Fire-and-Forget) で初期化
    spot = Spot(
        name="tracking_test",
        db=SQLiteTaskDB(db_path),
        storage_backend=slow_storage,
        serializer=MagicMock(),  # デコード不要のためモックでOK
        default_wait=False,
        default_save_blob=True,
    )
    return spot, slow_storage


def test_flush_on_context_exit(spot_with_slow_storage):
    """
    withブロックを抜ける際にバックグラウンドタスクの完了を待機するかを検証。
    """
    spot, _ = spot_with_slow_storage

    @spot.mark
    def my_task(x):
        return x

    start_time = time.time()

    with spot:
        # タスク実行
        res = my_task(10)
        assert res == 10

        # default_wait=False なので、0.5秒待たずにここに来るはず
        elapsed_inside = time.time() - start_time
        assert elapsed_inside < 0.2, (
            "Inside with-block, it should not wait for storage save."
        )

    # withブロックを抜けた後
    # ここで __exit__ による wait() が走り、0.5秒経過しているはず
    total_elapsed = time.time() - start_time
    assert total_elapsed >= 0.5, "On context exit, it should wait for background tasks."


def test_spot_reusability(spot_with_slow_storage):
    """
    一度withブロックを抜けても、Executorがシャットダウンされず再利用できるか検証。
    """
    spot, _ = spot_with_slow_storage

    @spot.mark
    def my_task(x):
        return x

    # 1回目の利用
    with spot:
        my_task(1)

    # 2回目の利用 (以前の仕様ではここで RuntimeError になっていた)
    try:
        with spot:
            my_task(2)
    except RuntimeError as e:
        pytest.fail(f"Spot should be reusable, but failed with: {e}")

    # 両方のタスクが保存されているか確認
    df = spot.db.get_history()
    assert len(df) == 2


@pytest.mark.asyncio
async def test_async_task_tracking(tmp_path):
    """非同期タスクのバックグラウンド実行が追跡されるか検証"""
    db_path = tmp_path / "async_test.db"

    # 非同期でも待機が必要なモック
    slow_storage = MagicMock()
    slow_storage.save.side_effect = lambda k, d: time.sleep(0.3) or "path"

    spot = Spot(
        "async_tracking",
        db=SQLiteTaskDB(db_path),
        storage_backend=slow_storage,
        serializer=MagicMock(),
        default_wait=False,
    )

    @spot.mark(save_blob=True)
    async def async_task(x):
        return x

    start_time = time.time()
    with spot:
        await async_task(1)
        # 0.3秒の保存を待たずに return される
        assert time.time() - start_time < 0.1

    # withを抜ける時に 0.3秒待たされる
    assert time.time() - start_time >= 0.3
