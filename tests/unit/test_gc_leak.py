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


def test_db_writer_thread_cleanup_on_gc(tmp_path):
    db_path = tmp_path / "test.db"
    blob_dir = tmp_path / "blobs"

    db = SQLiteTaskDB(db_path)
    # ライタースレッドが生きていることを確認
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

    # バックグラウンドリソースを初期化させるために一度保存を試みる
    @spot.mark(save_sync=False)
    def dummy():
        return 1

    dummy()

    # この時点で Spot の _finalizer がセットされているはず
    assert spot._finalizer is not None

    # dummy 関数が spot を参照し続けているので削除する
    del dummy

    # Spot インスタンスを削除
    del spot
    gc.collect()

    # 猶予を与える
    time.sleep(1.0)

    # ライタースレッドが停止していることを確認
    assert not writer_thread.is_alive(), (
        "DB writer thread should be stopped after Spot is GC'd"
    )


def test_manual_shutdown_still_works(tmp_path):
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

    # ensure_bg_resources を呼んで finalizer を作成しておく
    spot._ensure_bg_resources()

    spot.shutdown(save_sync=False)
    # スレッドの終了を少し待つ
    time.sleep(0.5)
    assert not writer_thread.is_alive()
    assert not spot._finalizer.alive
