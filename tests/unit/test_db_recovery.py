import threading
import time
import pytest
from beautyspot.db import SQLiteTaskDB, WriterTaintedError

def test_db_tainted_and_reset(tmp_path):
    # タイムアウトを極端に短く設定 (0.1s)
    db = SQLiteTaskDB(tmp_path / "test.db", timeout=0.1)
    db.init_schema()

    # interrupt() が効かないように Python レベルでブロックするタスク
    gate = threading.Event()
    def hanging_op(conn):
        gate.wait(timeout=2.0) # ブロック
        return "done"

    # 1. 最初のタスクを投入。これがタイムアウトして Tainted になるはず。
    # 実行中のタスクなので、0.1s 経過後に interrupt() が呼ばれ、さらに 1.0s 待機した後に Tainted になる。
    start = time.monotonic()
    with pytest.raises(WriterTaintedError) as exc:
        db._enqueue_write(hanging_op)
    elapsed = time.monotonic() - start

    assert elapsed >= 1.1 # 0.1s (timeout) + 1.0s (interrupt wait)
    assert "is now tainted" in str(exc.value).lower()
    assert db._writer_tainted is True

    # 2. 以降、reset() なしではすべての書き込みが即座に失敗することを確認
    with pytest.raises(WriterTaintedError):
        db._enqueue_write(lambda conn: "still tainted")

    # 3. reset() を実行して回復を試みる
    db.reset()
    assert db._writer_tainted is False
    assert db._writer_generation == 1

    # 4. 再び書き込みができることを確認
    assert db._enqueue_write(lambda conn: "recovered") == "recovered"

    # 後片付け
    gate.set()
    db.shutdown()
