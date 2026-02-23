# tests/integration/core/test_exit_drain.py

import gc
import time
import threading
from unittest.mock import MagicMock
import pytest

from beautyspot.core import Spot, _active_loops

@pytest.fixture(autouse=True)
def clean_active_loops():
    """テスト間の状態干渉を防ぐ"""
    _active_loops.clear()
    yield
    _active_loops.clear()

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
            name="temp", db=mock_db, serializer=mock_serializer,
            storage_backend=mock_storage, storage_policy=mock_policy, limiter=mock_limiter
        )
        # 保存ロジックをモックに差し替え
        spot._save_result_sync = slow_mock_save 
        
        # wait=Falseで非同期保存を投入
        spot._submit_background_save(
            cache_key="test_key", func_name="test", input_id="1", 
            version="1", result="data", content_type=None, 
            save_blob=False, serializer=None, expires_at=None
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
    
    assert success, "GC後にバックグラウンドタスクが完遂されずに破棄されました（データロスト）"

