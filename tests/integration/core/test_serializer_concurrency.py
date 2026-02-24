# tests/integration/core/test_serializer_concurrency.py

from concurrent.futures import ThreadPoolExecutor
from beautyspot.serializer import MsgpackSerializer


def test_msgpack_serializer_lru_cache_thread_safety():
    """
    複数スレッドから同時に動的な型をシリアライズした際、
    競合状態による LRU キャッシュのサイズ超過が発生しないことを検証する。
    """
    MAX_CACHE_SIZE = 50
    serializer = MsgpackSerializer(max_cache_size=MAX_CACHE_SIZE)

    class BaseDummy:
        pass

    serializer.register(BaseDummy, 1, lambda obj: {"v": 1}, lambda d: BaseDummy())

    def serialize_worker(worker_id: int):
        # max_cache_size を超える数の動的クラスを生成してシリアライズ
        for i in range(100):
            DynamicClass = type(f"DynamicDummy_{worker_id}_{i}", (BaseDummy,), {})
            instance = DynamicClass()
            serializer.dumps(instance)
        # スレッドごとにキャッシュサイズが守られていることを確認
        assert len(serializer._get_local_cache()) <= MAX_CACHE_SIZE

    # 10スレッドで一斉に1000個の型をシリアライズ
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(serialize_worker, i) for i in range(10)]
        for future in futures:
            future.result()
