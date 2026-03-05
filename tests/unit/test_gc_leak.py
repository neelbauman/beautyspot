import gc
import time
import beautyspot as bs
from beautyspot.db import SQLiteTaskDB
from beautyspot.storage import create_storage, AlwaysBlobPolicy
from beautyspot.serializer import MsgpackSerializer


class NoLimiter:
    def consume(self, cost: int) -> None:
        pass

    async def consume_async(self, cost: int) -> None:
        pass


def test_db_remains_alive_on_spot_gc(tmp_path):
    """
    Spot インスタンスが GC されても、DI で注入された DB インスタンスは
    勝手にシャットダウンされない（ライフサイクルが分離されている）ことを確認する。
    """
    db_path = tmp_path / "test.db"
    blob_dir = tmp_path / "blobs"

    db = SQLiteTaskDB(db_path)
    assert db._writer_thread.is_alive()
    writer_thread = db._writer_thread

    spot = bs.Spot(
        name="test_gc",
        db=db,
        serializer=MsgpackSerializer(),
        storage_backend=create_storage(str(blob_dir)),
        storage_policy=AlwaysBlobPolicy(),
        limiter=NoLimiter(),
    )

    @spot.mark(save_sync=False)
    def dummy():
        return 1

    dummy()

    assert spot._finalizer is not None

    del dummy
    del spot
    gc.collect()

    time.sleep(1.0)

    # 【変更点】 Spot が GC されても、DBのライタースレッドは生きているべき
    assert writer_thread.is_alive(), (
        "DB writer thread should NOT be stopped when Spot is GC'd (DI principle)"
    )

    # 呼び出し元の責任で DB をクリーンアップする
    db.shutdown(wait=True)
    time.sleep(0.5)
    assert not writer_thread.is_alive()


def test_spot_shutdown_does_not_close_db(tmp_path):
    """
    Spot の明示的な shutdown() を呼んでも、DB はクローズされないことを確認する。
    """
    db_path = tmp_path / "test2.db"
    db = SQLiteTaskDB(db_path)
    writer_thread = db._writer_thread

    spot = bs.Spot(
        name="test_manual",
        db=db,
        serializer=MsgpackSerializer(),
        storage_backend=create_storage(str(tmp_path / "blobs2")),
        storage_policy=AlwaysBlobPolicy(),
        limiter=NoLimiter(),
    )

    spot._ensure_bg_resources()

    spot.shutdown(save_sync=False)
    time.sleep(0.5)

    # 【変更点】 Spot のバックグラウンドリソースは解放されるが、DB は生きている
    assert writer_thread.is_alive()
    assert not spot._finalizer.alive

    # 呼び出し元の責任で DB をクリーンアップ
    db.shutdown(wait=True)
    time.sleep(0.5)
    assert not writer_thread.is_alive()
