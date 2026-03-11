# tests/unit/test_db_timeout_hard.py

import sqlite3
import threading
import time
import pytest
from beautyspot.db import SQLiteTaskDB

def test_db_timeout_running_interrupts_and_fails_fast(tmp_path):
    """
    修正後の挙動: RUNNING 状態のタスクは timeout を超えると interrupt() され、
    呼び出し元に TimeoutError が返る（フェイルファスト）。
    """
    # タイムアウトを短く設定 (0.5秒)
    db = SQLiteTaskDB(tmp_path / "test.db", timeout=0.5)
    db.init_schema()

    interrupted_event = threading.Event()
    
    def slow_op(conn: sqlite3.Connection):
        try:
            # RUNNING 状態で停止
            # gate.wait() は Python レベルの待機なので interrupt() では中断されないが、
            # SQLite のクエリ実行中であれば中断される。
            # ここではダミーの重いクエリ（あるいは無限ループに近いもの）を想定。
            # 実際には conn.execute("...") が interrupted エラーを投げる。
            conn.execute("WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM t LIMIT 10000000) SELECT count(*) FROM t")
        except (sqlite3.OperationalError, sqlite3.ProgrammingError) as e:
            if "interrupted" in str(e).lower() or "callback" in str(e).lower():
                interrupted_event.set()
            raise
        return "done"

    # タイムアウトが発生することを確認
    start = time.monotonic()
    with pytest.raises(TimeoutError) as exc:
        db._enqueue_write(slow_op)
    elapsed = time.monotonic() - start

    # タイムアウト(0.5s) + interrupt待ち(最大1.0s) の範囲内で戻ってくること
    assert 0.5 <= elapsed < 2.0
    assert "timed out after 0.5s and" in str(exc.value)
    assert "interrupted" in str(exc.value) or "interrupt was attempted" in str(exc.value)

    # ライタースレッドが生きていることを確認（パニックしていないこと）
    assert db._writer_thread.is_alive()
    
    # 次の書き込みができることを確認（リカバリできていること）
    assert db._enqueue_write(lambda conn: "recovered") == "recovered"

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
    # PENDING の場合は interrupt 待ちがないので 0.5s 前後
    assert 0.5 <= elapsed < 1.0
    assert "did not start within 0.5s and was cancelled" in str(exc.value)
    
    gate.set()
    t_slow.join()
    db.shutdown()
