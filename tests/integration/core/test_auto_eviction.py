# tests/integration/core/test_auto_eviction.py

import concurrent.futures
from unittest.mock import patch

import beautyspot as bs


def test_auto_eviction_flag_cleared_on_future_cancel(tmp_path):
    """
    バックグラウンドに投入されたエビクションタスクが、
    イベントループのシャットダウン等によりキャンセルされた場合でも、
    確実に _eviction_running フラグがリセットされることを検証する。
    """
    # 確実にエビクションがトリガーされるよう eviction_rate=1.0 に設定
    spot = bs.Spot("test_app", eviction_rate=1.0)

    # 実行前の状態: フラグはリセットされている
    assert not spot._eviction_running

    # 内部リソースを初期化して取得
    bg_loop, _ = spot._ensure_bg_resources()

    # 手動で制御可能な concurrent.futures.Future を用意
    mock_future = concurrent.futures.Future()

    # RuntimeWarning(coroutine never awaited) 対策:
    # モックに渡されたコルーチンを明示的にクローズする
    def mock_submit(coro):
        coro.close()
        return mock_future

    # bg_loop.submit をモックに差し替え
    with patch.object(bg_loop, "submit", side_effect=mock_submit):
        spot._trigger_auto_eviction()

        # タスクが submit された直後。
        # まだ Future は完了していないため、多重起動防止フラグは True になっているべき
        assert spot._eviction_running is True

        # エッジケースのシミュレート: イベントループ停止により Future がキャンセルされた
        mock_future.cancel()

        # cancel() によって add_done_callback が発火し、フラグがリセットされているはず
        assert spot._eviction_running is False


def test_auto_eviction_flag_cleared_on_task_rejection(tmp_path):
    """
    シャットダウン中などの理由で bg_loop.submit がタスクを拒否し
    None を返した場合に、直ちにフラグがリセットされることを検証する。
    """
    spot = bs.Spot("test_app", eviction_rate=1.0)
    bg_loop, _ = spot._ensure_bg_resources()

    # RuntimeWarning対策: コルーチンを閉じてから None を返す
    def mock_submit_reject(coro):
        coro.close()
        return None

    # submit がタスクを拒否（Noneを返す）ケースをシミュレート
    with patch.object(bg_loop, "submit", side_effect=mock_submit_reject):
        spot._trigger_auto_eviction()

        # スケジュール自体に失敗したので、フラグは関数内で即座にリセットされていなければならない
        assert spot._eviction_running is False
