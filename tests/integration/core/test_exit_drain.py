# tests/integration/core/test_exit_drain.py

import subprocess
import sys
import time
import gc
import threading
from unittest.mock import MagicMock
from beautyspot.core import Spot


def test_zombie_thread_completes_tasks():
    """
    SpotインスタンスがGCによって破棄されても、バックグラウンドスレッドが
    自律的にタスクを完了（ゾンビ化）してデータロストを防ぐことを検証する。
    """
    task_completed_event = threading.Event()

    # 重いIO処理をシミュレートするモック保存関数
    def slow_mock_save(*args, **kwargs):
        time.sleep(0.1)  # 擬似的なIO待機
        task_completed_event.set()

    # モック用の依存オブジェクト
    mock_db = MagicMock()
    mock_db.init_schema = MagicMock()
    mock_serializer = MagicMock()
    mock_storage = MagicMock()
    mock_policy = MagicMock()
    mock_limiter = MagicMock()

    def run_temp_spot():
        # 関数ローカルなスコープでSpotを初期化
        spot = Spot(
            name="temp",
            db=mock_db,
            serializer=mock_serializer,
            storage_backend=mock_storage,
            storage_policy=mock_policy,
            limiter=mock_limiter,
        )
        # 保存ロジックをモックに差し替え
        spot._save_result_sync = slow_mock_save

        # wait=Falseで非同期保存を投入
        spot._submit_background_save(
            cache_key="test_key",
            func_name="test",
            input_id="1",
            version="1",
            result="data",
            content_type=None,
            save_blob=False,
            serializer=None,
            expires_at=None,
        )
        # 関数を抜けるとspotインスタンスは参照を失う

    run_temp_spot()

    # GCを強制実行し、_shutdown_resources を発火させる
    gc.collect()

    # 1. メインスレッドがブロックされていないことの確認
    # (即座にチェックするため、まだバックグラウンド処理は終わっていないはず)
    assert not task_completed_event.is_set(), "メインスレッドがブロックされています。"

    # 2. ゾンビスレッドがタスクを完遂することの確認
    # 最大1秒待機。成功すれば0.1秒強で通過する。
    success = task_completed_event.wait(timeout=1.0)

    assert success, (
        "GC後にバックグラウンドタスクが完遂されずに破棄されました（データロスト）"
    )


def test_background_loop_graceful_drain_on_exit(tmp_path):
    """
    正常系:
    atexit時、_BackgroundLoop がタイムアウト付きで
    未完了タスクを正しくドレイン（処理完了）して終了することを確認する。
    """
    script_path = tmp_path / "simulate_exit.py"
    flag_file = tmp_path / "done.flag"

    # 意図的に時間がかかるタスクを仕込み、すぐにメインプロセスを終了するスクリプト
    script_content = f"""
import asyncio
import sys
import logging
from beautyspot.core import _BackgroundLoop

logging.basicConfig(level=logging.INFO)
loop = _BackgroundLoop(drain_timeout=3.0)

async def slow_io_task():
    await asyncio.sleep(1.0)  # 1秒かかるIO処理をシミュレート
    with open(r'{flag_file}', 'w') as f:
        f.write('success')

# タスクを投入して即座にメインスレッドを終了（sys.exit）する
loop.submit(slow_io_task())
sys.exit(0)
    """
    script_path.write_text(script_content, encoding="utf-8")

    # スクリプトを実行
    start_time = time.time()
    result = subprocess.run(
        [sys.executable, str(script_path)], capture_output=True, text=True
    )
    elapsed = time.time() - start_time

    # 実行が成功していること
    assert result.returncode == 0
    # メインスレッド終了(sys.exit)後もスレッドが生き残り、1秒後のファイル書き込みが成功しているはず
    assert flag_file.exists(), f"File was not created. Stderr: {result.stderr}"
    assert flag_file.read_text(encoding="utf-8") == "success"
    # atexitでの待機が発生したため、実行時間は1秒以上かかっているはず
    assert elapsed >= 1.0


def test_background_loop_timeout_on_exit(tmp_path):
    """
    異常系（安全網）:
    atexit時、タスクが drain_timeout を超過した場合は無限ハングせずに
    強制終了（警告ログを出力）してプロセスが確実に終わることを確認する。
    """
    script_path = tmp_path / "simulate_timeout.py"
    flag_file = tmp_path / "done_timeout.flag"

    script_content = f"""
import asyncio
import sys
import logging
from beautyspot.core import _BackgroundLoop

# 標準エラー出力にログを出すように設定
logging.basicConfig(level=logging.WARNING)

# タイムアウトを極端に短く（1秒）設定
loop = _BackgroundLoop(drain_timeout=1.0)

async def too_slow_task():
    await asyncio.sleep(3.0)  # タイムアウト(1秒)より長くかかるタスク
    with open(r'{flag_file}', 'w') as f:
        f.write('success')

loop.submit(too_slow_task())
sys.exit(0)
    """
    script_path.write_text(script_content, encoding="utf-8")

    start_time = time.time()
    result = subprocess.run(
        [sys.executable, str(script_path)], capture_output=True, text=True
    )
    elapsed = time.time() - start_time

    assert result.returncode == 0
    # 3秒待たずに、タイムアウトの1秒強で強制終了しているはず
    assert elapsed < 2.0
    # タスクは完了前にキルされるため、ファイルは存在しないはず
    assert not flag_file.exists()
    # タイムアウト発生の警告ログが標準エラー出力に出ていることを確認
    assert "BeautySpot background loop did not finish within 1.0s" in result.stderr
