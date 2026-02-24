# tests/integration/core/test_async_save.py

import logging
import time
from unittest.mock import MagicMock, patch
from beautyspot import Spot
from beautyspot.db import SQLiteTaskDB
from beautyspot.types import SaveErrorContext


def test_shutdown_waits_for_pending_tasks(tmp_path):
    """
    default_wait=False の場合でも、Spotの終了時(Context Exit)には
    バックグラウンドの保存タスク完了を待機することを確認する。
    """
    db_path = tmp_path / "async_test.db"

    # モックを使って保存処理を遅延させる (0.5秒)
    # 実際のDB保存は一瞬で終わってしまうため、Storageをフックする
    slow_storage = MagicMock()

    def slow_save(key, data):
        time.sleep(2)
        return "mock_location"

    slow_storage.save.side_effect = slow_save

    # default_wait=False で初期化
    spot = Spot(
        "async_app",
        db=SQLiteTaskDB(db_path),
        storage_backend=slow_storage,  # Mockストレージ注入
        default_wait=False,  # ★ Fire-and-Forgetモード
        default_save_blob=True,  # Storageを使わせるため
    )

    call_count = 0

    @spot.mark
    def quick_task(x):
        nonlocal call_count
        call_count += 1
        return x

    # --- テスト実行 ---

    with spot:
        start_time = time.time()

        # 1. タスク実行
        # default_wait=False なので、0.5秒の保存を待たずに即座に返ってくるはず
        res = quick_task(10)

        elapsed = time.time() - start_time
        assert res == 10
        assert elapsed < 0.2, "ユーザー関数は保存を待たずに即終了すべき"

        # この時点ではまだ保存が完了していない（はず）
        # ※ DBへの書き込みは _save_result_sync の最後なので確認は難しいが
        # executorにはタスクが積まれている状態

    # --- Context Exit 後 ---

    # 2. 終了時間の検証
    # `with spot:` を抜ける際、executor.shutdown(wait=True) が呼ばれるため、
    # ここで少なくとも残りの時間（約0.5秒）待たされているはず。

    total_time = time.time() - start_time
    assert total_time >= 2.0, "Spotの終了時にバックグラウンドタスクを待機すべき"

    # 3. データ整合性の検証
    # ちゃんと保存処理が走ったか確認
    df = spot.db.get_history()
    assert len(df) == 1
    assert df.iloc[0]["result_type"] == "FILE"


def test_on_background_error_called_on_save_failure(mocker):
    """
    バックグラウンド保存 (wait=False) 中に _save_result_sync が例外を投げた場合、
    on_background_error コールバックが正しい引数で呼ばれることを検証する。
    """
    # Arrange: コールバックのモックを作成
    mock_callback = MagicMock()

    # Spotインスタンスの作成（依存関係は適宜モック化されている前提）
    # ※ 実際のプロジェクトの fixture (例: mock_db, mock_serializer等) に合わせて調整してください
    spot = Spot(
        name="test_spot",
        db=MagicMock(),
        serializer=MagicMock(),
        storage_backend=MagicMock(),
        storage_policy=MagicMock(),
        limiter=MagicMock(),
        default_wait=False,  # バックグラウンド実行をデフォルトに
        on_background_error=mock_callback,
    )

    # _save_result_sync が意図的に例外を投げるようにモック化
    test_exception = RuntimeError("Disk full!")
    mocker.patch.object(spot, "_save_result_sync", side_effect=test_exception)

    @spot.mark()
    def dummy_task(x):
        return x * 2

    # Act: 関数を実行 (wait=False なので保存処理は裏で走る)
    result = dummy_task(10)

    # バックグラウンドタスクの完了を待機 (Spot.__exit__ の仕組みを利用するか、手動で wait する)
    spot.shutdown(wait=True)

    # Assert: 戻り値自体は正常に計算されていること
    assert result == 20

    # コールバックが1回呼ばれていること
    mock_callback.assert_called_once()

    # 呼ばれた際の引数を検証
    args, _ = mock_callback.call_args
    passed_exception, passed_context = args

    assert passed_exception is test_exception
    assert isinstance(passed_context, SaveErrorContext)
    assert passed_context.func_name == "dummy_task"
    assert passed_context.result == 20
    # cache_key 等が kwargs から正しく渡されているかも検証可能


def test_on_background_error_does_not_crash_thread(mocker, caplog):
    """
    on_background_error コールバック自体が例外を投げた場合でも、
    スレッドがクラッシュせずにエラーがログに記録されることを検証する。
    """

    # Arrange: 呼ばれると例外を投げる悪意のある（？）コールバック
    def faulty_callback(err, context):
        raise ValueError("Error inside callback!")

    spot = Spot(
        name="test_spot_faulty",
        db=MagicMock(),
        serializer=MagicMock(),
        storage_backend=MagicMock(),
        storage_policy=MagicMock(),
        limiter=MagicMock(),
        default_wait=False,
        on_background_error=faulty_callback,
    )

    mocker.patch.object(
        spot, "_save_result_sync", side_effect=RuntimeError("Save failed")
    )

    @spot.mark()
    def dummy_task():
        return "ok"

    # Act
    dummy_task()
    spot.shutdown(wait=True)

    # Assert: ログにコールバック内部のエラーが出力されていることを確認
    assert "Error occurred within the 'on_background_error' callback" in caplog.text
    assert "Error inside callback!" in caplog.text


def test_background_save_notifies_on_shutdown_rejection():
    """
    シャットダウン後の submit 時に on_background_error が呼ばれ、
    ログにも警告が出ることを検証する。
    """
    mock_callback = MagicMock()

    spot = Spot(
        name="test_notify",
        db=MagicMock(),
        serializer=MagicMock(),
        storage_backend=MagicMock(),
        storage_policy=MagicMock(),
        limiter=MagicMock(),
        default_wait=False,
        on_background_error=mock_callback,
    )

    # バックグラウンドリソースを初期化してからシャットダウン
    spot._ensure_bg_resources()
    spot.shutdown(wait=True)

    # シャットダウン後に _submit_background_save を呼ぶ
    save_kwargs = {
        "cache_key": "test_key",
        "func_name": "my_func",
        "func_identifier": "tests.integration.core.test_async_save.my_func",
        "input_id": "abc",
        "version": "v1",
        "result": 42,
        "content_type": None,
        "save_blob": None,
        "expires_at": None,
    }

    with patch("beautyspot.core.logger") as mock_logger:
        spot._submit_background_save(**save_kwargs)

        # 警告ログが出力されていること
        mock_logger.warning.assert_called_once()
        log_msg = mock_logger.warning.call_args[0][0]
        assert "my_func" in log_msg
        assert "discarded" in log_msg

    # on_background_error コールバックが呼ばれていること
    mock_callback.assert_called_once()
    err, ctx = mock_callback.call_args[0]
    assert isinstance(err, RuntimeError)
    assert "my_func" in str(err)
    assert isinstance(ctx, SaveErrorContext)
    assert ctx.func_name == "my_func"
    assert ctx.cache_key == "test_key"
    assert ctx.result == 42


def test_background_save_logs_warning_without_callback(caplog):
    """
    on_background_error コールバック未設定でも、
    シャットダウン拒否時にログ警告が出ることを検証する。
    """
    spot = Spot(
        name="test_no_callback",
        db=MagicMock(),
        serializer=MagicMock(),
        storage_backend=MagicMock(),
        storage_policy=MagicMock(),
        limiter=MagicMock(),
        default_wait=False,
        on_background_error=None,  # コールバック未設定
    )

    spot._ensure_bg_resources()
    spot.shutdown(wait=True)

    save_kwargs = {
        "cache_key": "key2",
        "func_name": "another_func",
        "func_identifier": "tests.integration.core.test_async_save.another_func",
        "input_id": "xyz",
        "version": None,
        "result": "data",
        "content_type": None,
        "save_blob": None,
        "expires_at": None,
    }

    with caplog.at_level(logging.WARNING, logger="beautyspot.core"):
        spot._submit_background_save(**save_kwargs)

    assert "another_func" in caplog.text
    assert "discarded" in caplog.text
