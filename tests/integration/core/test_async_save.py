# tests/integration/core/test_async_save.py

import time
from unittest.mock import MagicMock
from beautyspot import Spot
from beautyspot.db import SQLiteTaskDB

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
        default_wait=False,    # ★ Fire-and-Forgetモード
        default_save_blob=True # Storageを使わせるため
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

