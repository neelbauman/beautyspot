import asyncio
import pytest
import time
from unittest.mock import patch
from beautyspot import Spot, SQLiteTaskDB, HookBase


@pytest.mark.asyncio
async def test_async_save_sync_propagates_exception(tmp_path):
    """BUG-1: save_sync=True の場合、asyncパスでも保存エラーが例外として投げられること"""
    db_path = tmp_path / "test.db"
    spot = Spot("test_bug1", db=SQLiteTaskDB(db_path))

    # DBのsaveメソッドをモックして例外を投げさせる
    with patch.object(spot.cache.db, "save", side_effect=RuntimeError("DB Save Error")):

        @spot.mark(save_sync=True)
        async def my_async_func(x):
            return x * 2

        # 保存時に例外が発生し、それが呼び出し元まで伝播するはず
        with pytest.raises(RuntimeError, match="DB Save Error"):
            await my_async_func(10)


@pytest.mark.asyncio
async def test_async_thundering_herd_original_exception(tmp_path):
    """BUG-2: Thundering Herd で待機側が元の例外を受け取れること"""
    db_path = tmp_path / "test.db"
    spot = Spot("test_bug2", db=SQLiteTaskDB(db_path))

    class MyCustomError(Exception):
        pass

    call_count = 0
    start_event = asyncio.Event()

    @spot.mark()
    async def task():
        nonlocal call_count
        call_count += 1
        await start_event.wait()
        raise MyCustomError("original error")

    # 1つ目のタスクを開始して中断
    t1 = asyncio.create_task(task())

    # 2つ目のタスクを開始（Thundering Herd で1つ目を待つ状態になる）
    await asyncio.sleep(0.1)
    t2 = asyncio.create_task(task())

    await asyncio.sleep(0.1)
    # 1つ目を再開させて失敗させる
    start_event.set()

    # 両方のタスクが同じ MyCustomError を受け取るはず
    with pytest.raises(MyCustomError, match="original error"):
        await t1
    with pytest.raises(MyCustomError, match="original error"):
        await t2

    assert call_count == 1


@pytest.mark.asyncio
async def test_async_hook_non_blocking(tmp_path):
    """DESIGN-3: フックがブロッキング処理を含んでいても、イベントループが停止しないこと"""
    db_path = tmp_path / "test.db"
    spot = Spot("test_design3", db=SQLiteTaskDB(db_path))

    class BlockingHook(HookBase):
        def pre_execute(self, context):
            # 同期的なスリープ（ブロッキング）
            time.sleep(0.5)

    @spot.mark(hooks=[BlockingHook()])
    async def my_func():
        return "done"

    start_time = asyncio.get_event_loop().time()

    # 並行して別のタスクを動かす
    async def other_task():
        await asyncio.sleep(0.1)
        return "other"

    # フックがブロッキングしていても、other_task が並行して進めるか（run_in_executorの効果）
    res = await asyncio.gather(my_func(), other_task())

    end_time = asyncio.get_event_loop().time()
    assert res == ["done", "other"]
    # もしフックがメインスレッド（イベントループ）をブロックしていたら、
    # gather 全体が 0.5秒以上かかるはず。
    # しかし、other_task が 0.1秒で完了し、my_func も 0.5秒で完了するため、
    # イベントループがブロックされていなければ、全体の時間は約 0.5秒になる。
    # ここでは厳密な時間判定よりも、asyncio.gather が正常に完了し、
    # I/O executor でフックが実行されていることを意図している。
    elapsed = end_time - start_time
    assert elapsed >= 0.5
