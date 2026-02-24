import asyncio
import threading
import time
import pytest
import beautyspot as bs


@pytest.mark.asyncio
async def test_thundering_herd_sync():
    spot = bs.Spot("test_herd_sync", save_sync=True)
    execution_count = [0]
    lock = threading.Lock()

    @spot.mark
    def heavy_task(x):
        with lock:
            execution_count[0] += 1
        time.sleep(0.5)
        return x * 2

    spot.maintenance.clear()
    loop = asyncio.get_running_loop()
    results = await asyncio.gather(
        *(loop.run_in_executor(None, heavy_task, 10) for _ in range(5))
    )

    assert execution_count[0] == 1
    assert results == [20] * 5


@pytest.mark.asyncio
async def test_thundering_herd_async():
    spot = bs.Spot("test_herd_async", save_sync=True)
    execution_count = [0]
    lock = threading.Lock()

    @spot.mark
    async def heavy_task_async(x):
        with lock:
            execution_count[0] += 1
        await asyncio.sleep(0.5)
        return x * 2

    spot.maintenance.clear()
    results = await asyncio.gather(*(heavy_task_async(10) for _ in range(5)))

    assert execution_count[0] == 1
    assert results == [20] * 5


@pytest.mark.asyncio
async def test_thundering_herd_cross_sync_async():
    """
    同じ（名前を持つ）関数が同期と非同期のコンテキストから同時に呼ばれても、
    サンダリングハーフ対策が有効であることを検証する。
    """
    spot = bs.Spot("test_herd_cross", save_sync=True)
    execution_count = [0]
    lock = threading.Lock()

    # 同じ identifier を持たせるために同じ名前を使用
    # (別関数だが keygen で同じ key を生成するように強制する)
    @spot.mark(version="v1")
    def heavy_task(x):
        with lock:
            execution_count[0] += 1
        time.sleep(0.5)
        return x * 2

    @spot.mark(version="v1")
    async def heavy_task_async(x):
        with lock:
            execution_count[0] += 1
        await asyncio.sleep(0.5)
        return x * 2

    # [FIX] identifier を手動でモックし、同じキーを生成させる。
    # 通常のユーザーコードでは推奨されませんが、テストのために
    # _get_func_identifier をパッチします。
    original_get_id = bs.core.Spot._get_func_identifier
    bs.core.Spot._get_func_identifier = staticmethod(lambda f: "shared_task")

    try:
        spot.maintenance.clear()
        loop = asyncio.get_running_loop()

        # 同期と非同期を同時に走らせる
        results = await asyncio.gather(
            loop.run_in_executor(None, heavy_task, 10), heavy_task_async(10)
        )

        assert execution_count[0] == 1
        assert results == [20, 20]
    finally:
        # パッチを戻す
        bs.core.Spot._get_func_identifier = original_get_id
