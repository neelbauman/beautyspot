# tests/unit/test_db_timeout_hard.py

import sqlite3
import threading
import time
import pytest
from beautyspot.db import SQLiteTaskDB

def test_db_timeout_running_waits_indefinitely(tmp_path):
    """
    現在の挙動: RUNNING 状態のタスクは timeout を超えても待ち続ける。
    """
    # タイムアウトを極端に短く設定 (0.5秒)
    db = SQLiteTaskDB(tmp_path / "test.db", timeout=0.5)
    db.init_schema()

    gate = threading.Event()
    
    def slow_op(conn: sqlite3.Connection):
        # RUNNING 状態で停止
        gate.wait(timeout=2.0)
        return "done"

    time.monotonic()
    
    # 別スレッドで実行を開始させる (RUNNING 状態にするため)
    def call_enqueue():
        try:
            db._enqueue_write(slow_op)
        except Exception:
            # エラーが発生した場合は記録 (修正後にここに来るはず)
            pass

    t = threading.Thread(target=call_enqueue)
    t.start()
    
    # タイムアウト(0.5s)を十分に過ぎるまで待つ
    time.sleep(1.0)
    
    # まだスレッドが終了していない（＝待ち続けている）ことを確認
    assert t.is_alive()
    
    # 解放して終了させる
    gate.set()
    t.join(timeout=1.0)
    db.shutdown()

def test_db_timeout_pending_cancels(tmp_path):
    """
    既存の挙動: PENDING 状態（未着手）のタスクは timeout でキャンセルされる。
    """
    db = SQLiteTaskDB(tmp_path / "test.db", timeout=0.5)
    db.init_schema()
    
    # 1つ目の重いタスクで Writer Thread を占有
    gate = threading.Event()
    def slow_op(conn):
        gate.wait(timeout=2.0)

    t_slow = threading.Thread(target=lambda: db._enqueue_write(slow_op))
    t_slow.start()
    
    # 2つ目のタスクを投入。1つ目が終わるまで PENDING になる。
    start = time.monotonic()
    with pytest.raises(TimeoutError) as exc:
        db._enqueue_write(lambda conn: "should fail")
    
    elapsed = time.monotonic() - start
    assert 0.5 <= elapsed < 1.0
    assert "did not start within 0.5s and was cancelled" in str(exc.value)
    
    gate.set()
    t_slow.join()
    db.shutdown()
