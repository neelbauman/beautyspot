
import sqlite3
import threading
import pytest
from beautyspot.db import SQLiteTaskDB

def test_sqlite_read_connection_recovery(tmp_path):
    """BUG-3: 壊れた読み取り接続からの回復テスト"""
    db_path = tmp_path / "test.db"
    db = SQLiteTaskDB(db_path)
    db.init_schema()
    
    # 正常な読み取り
    with db._read_connect() as conn:
        conn.execute("SELECT 1").fetchone()
    
    # スレッドローカルに接続が保持されていることを確認
    assert db._local.read_conn_wrapper is not None
    original_conn = db._local.read_conn_wrapper.conn
    
    # 接続を強制的にクローズして「壊れた状態」にする
    original_conn.close()
    
    # 次の読み取りで sqlite3.Error (または ProgrammingError) が発生するが、
    # _read_connect 内で検知してリカバリされるはず
    with pytest.raises(sqlite3.Error):
        with db._read_connect() as conn:
            conn.execute("SELECT 1").fetchone()
            
    # リカバリにより、スレッドローカルの wrapper が None にリセットされているはず
    assert db._local.read_conn_wrapper is None
    
    # 次のアクセスでは新しい接続が作られ、正常に動くはず
    with db._read_connect() as conn:
        res = conn.execute("SELECT 1").fetchone()
        assert res[0] == 1
        assert conn is not original_conn

def test_sqlite_read_connection_leak_prevention(tmp_path):
    """BUG-4: スレッド終了時に接続がリークしないことの検証"""
    db_path = tmp_path / "test.db"
    db = SQLiteTaskDB(db_path)
    db.init_schema()
    
    def worker():
        with db._read_connect() as conn:
            conn.execute("SELECT 1").fetchone()
        # ここでスレッドが終了する
    
    # 初期状態
    assert len(db._read_wrappers) == 0
    
    t = threading.Thread(target=worker)
    t.start()
    t.join()
    
    # WeakSet なので、スレッド終了に伴い wrapper が GC されれば
    # 自動的にセットから消えるはず（GCのタイミングに依存する可能性があるが）
    import gc
    gc.collect()
    
    # wrapper が __del__ で close() を呼ぶため、ファイルハンドルもリークしない
    assert len(db._read_wrappers) == 0
