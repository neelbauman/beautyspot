# tests/integration/core/test_exit_drain.py

"""__exit__ ドレインループのテスト。"""

import time
from unittest.mock import MagicMock

import beautyspot as bs
from beautyspot.db import SQLiteTaskDB


def test_exit_drains_all_pending_futures(tmp_path):
    """__exit__ が保留中のすべてのバックグラウンド保存を待つことを確認する。"""
    slow_storage = MagicMock()
    save_count = 0

    def slow_save(key, data):
        nonlocal save_count
        time.sleep(0.3)
        save_count += 1
        return f"loc_{save_count}"

    slow_storage.save.side_effect = slow_save

    spot = bs.Spot(
        name="drain_test",
        db=SQLiteTaskDB(tmp_path / "d.db"),
        storage_backend=slow_storage,
        default_wait=False,
        default_save_blob=True,
    )

    @spot.mark()
    def fn(x):
        return x

    with spot:
        # 複数のバックグラウンド保存を投入
        for i in range(3):
            fn(i)

    # __exit__ 後は全保存が完了しているべき
    assert save_count == 3


def test_exit_does_not_stop_loop(tmp_path):
    """__exit__ 後もバックグラウンドループは停止せず、再利用可能であることを確認する。"""
    spot = bs.Spot(
        name="reuse_test",
        db=SQLiteTaskDB(tmp_path / "r.db"),
        storage_backend=bs.LocalStorage(tmp_path / "blobs"),
        default_wait=False,
    )

    @spot.mark()
    def fn(x):
        return x

    # 1回目
    with spot:
        fn(1)

    # 2回目: ループが生きていれば正常に動作する
    with spot:
        fn(2)

    rows = spot.db.get_history()
    assert len(rows) == 2


def test_drain_handles_empty_futures(tmp_path):
    """保留中の Future がない場合も __exit__ が正常に終了することを確認する。"""
    spot = bs.Spot(
        name="empty_test",
        db=SQLiteTaskDB(tmp_path / "e.db"),
        storage_backend=bs.LocalStorage(tmp_path / "blobs"),
    )

    @spot.mark()
    def fn(x):
        return x

    # wait=True (default) なのでバックグラウンド Future はない
    with spot:
        fn(1)

    # 正常終了のみ確認
    rows = spot.db.get_history()
    assert len(rows) == 1
