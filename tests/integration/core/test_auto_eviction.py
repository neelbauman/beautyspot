import threading
from unittest.mock import patch

import pytest

import beautyspot as bs
from beautyspot.db import SQLiteTaskDB


def test_eviction_rate_validation(tmp_path):
    """
    Spotの初期化時に eviction_rate のバリデーションが正しく機能するかテストする。
    """
    # 負の値は不可
    with pytest.raises(ValueError, match="eviction_rate must be between"):
        bs.Spot("test_app", eviction_rate=-0.1)

    # 1.0を超える値は不可
    with pytest.raises(ValueError, match="eviction_rate must be between"):
        bs.Spot("test_app", eviction_rate=1.1)

    # 正常な値
    spot = bs.Spot("test_app", eviction_rate=0.5)
    assert spot.eviction_rate == 0.5


def test_auto_eviction_trigger_probability(tmp_path):
    """
    確率に応じてバックグラウンドループにクリーンアップ処理が投入されるかをテストする。
    """
    spot = bs.Spot("test_app", eviction_rate=0.5)

    # _trigger_auto_eviction 内での clean_garbage の実行を監視
    with patch.object(spot.maintenance, "clean_garbage") as mock_clean:
        # パターン1: 乱数が閾値未満 (0.1 < 0.5) -> トリガーされるべき
        with patch("random.random", return_value=0.1):
            spot._trigger_auto_eviction()

            # バックグラウンドループ上のタスクが完了するのを待機
            spot.shutdown(wait=True)
            mock_clean.assert_called_once()

    # Spotを作り直してパターン2をテスト
    spot2 = bs.Spot("test_app2", eviction_rate=0.5)

    with patch.object(spot2.maintenance, "clean_garbage") as mock_clean2:
        # パターン2: 乱数が閾値以上 (0.9 >= 0.5) -> トリガーされないべき
        with patch("random.random", return_value=0.9):
            spot2._trigger_auto_eviction()

            spot2.shutdown(wait=True)
            mock_clean2.assert_not_called()


def test_maintenance_try_lock(tmp_path):
    """
    MaintenanceService.clean_garbage が複数のスレッドから同時に呼ばれた際、
    Try-Lock によって1つのスレッドのみが実行し、他がスキップされるかをテストする。
    """
    spot = bs.Spot("test_app")
    maintenance = spot.maintenance

    # スレッド間の同期制御用イベント
    in_clean_event = threading.Event()
    resume_clean_event = threading.Event()

    # 意図的に処理を遅延させるモックメソッドを作成
    original_delete_expired = maintenance.delete_expired_tasks

    def slow_delete_expired():
        # 掃除処理に入ったことを通知
        in_clean_event.set()
        # メインスレッドからの再開合図を待機 (ここでロックを保持したまま止まる)
        resume_clean_event.wait()
        return original_delete_expired()

    # delete_expired_tasks をモックに差し替え
    maintenance.delete_expired_tasks = slow_delete_expired

    results = []

    def run_clean():
        # clean_garbageの戻り値を記録
        results.append(maintenance.clean_garbage())

    # 2つのスレッドを用意
    t1 = threading.Thread(target=run_clean)
    t2 = threading.Thread(target=run_clean)

    # t1 を開始
    t1.start()

    # t1 がロックを取得し、slow_delete_expired の中で止まるのを待つ
    in_clean_event.wait()

    # この時点でロックは t1 に保持されているので、t2 を開始する
    # t2 はロックを取得できず、即座に (0, 0) を返して終了するはず
    t2.start()
    t2.join()

    # t1 の処理を再開させる
    resume_clean_event.set()
    t1.join()

    # 検証
    assert len(results) == 2
    # 少なくとも一方はスキップされて (0, 0) を返しているはず
    assert (0, 0) in results


def test_auto_eviction_with_wait_false(tmp_path):
    """
    wait=False (バックグラウンド保存) のタスク実行時にも、
    正しく自動エビクションがバックグラウンドでエンキューされ、処理されるかをテストする。
    """
    # 確実にトリガーさせるために eviction_rate=1.0 に設定
    spot = bs.Spot(
        "test_bg_with_wait_false",
        db=SQLiteTaskDB(tmp_path / "test_bg_with_fait_false"),
        eviction_rate=1.0,
    )

    # wait=False でマーク
    @spot.mark(wait=False)
    def fast_task(x: int):
        return x * 2

    with patch.object(spot.maintenance, "clean_garbage") as mock_clean:
        # タスク実行（キャッシュミス -> 保存と掃除がバックグラウンドへ）
        # wait=False なので、この呼び出しはメインスレッドをブロックせず即座に返る
        result = fast_task(10)
        assert result == 20

        # この時点ではバックグラウンドスレッドが処理中かもしれないので、
        # assert_called_once() をすぐ呼ぶとFlaky(不安定)になる可能性がある。
        # 確実に完了を待機(ドレイン)するために shutdown(wait=True) を呼ぶ。
        spot.shutdown(wait=True)

        # 保存完了後、正しく clean_garbage が呼ばれたか検証
        mock_clean.assert_called_once()

    # (念のため) もう一度実行してキャッシュヒットさせる
    with patch.object(spot.maintenance, "clean_garbage") as mock_clean_hit:
        # キャッシュヒット時はDBへの新規保存が発生しないため、
        # 掃除(エビクション)もトリガーされるべきではない
        result2 = fast_task(10)
        assert result2 == 20

        spot.shutdown(wait=True)
        mock_clean_hit.assert_not_called()
