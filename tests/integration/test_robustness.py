# tests/integration/test_robustness.py

import pytest
import asyncio
import time
import sqlite3
from dataclasses import dataclass
from beautyspot import Spot

# --- 1. Custom Data Structure ---
@dataclass
class CriticalData:
    id: str
    payload: bytes  # バイナリデータの整合性もチェック

def encode_critical(obj: CriticalData) -> list:
    return [obj.id, obj.payload]

def decode_critical(data: list) -> CriticalData:
    return CriticalData(id=data[0], payload=data[1])

# --- 2. Helper for White-box Verification ---
def inspect_db_counts(db_path: str) -> dict:
    """
    SQLiteDBを直接覗き見て、タスクの状態を集計するヘルパー。
    beautyspotのAPIを経由しないため、ごまかしが効かない。
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT count(*) FROM tasks")
        total = cursor.fetchone()[0]
        
        # 成功/失敗のステータス概念がDBスキーマにある場合はここで集計
        # 現状のスキーマ(core.py参照)では結果があれば成功とみなせる
        return {"total_records": total}

def inspect_db_record(db_path: str, cache_key: str):
    """特定のキャッシュキーのレコードが生で存在するか確認"""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT func_name, result_type FROM tasks WHERE cache_key=?", 
            (cache_key,)
        ).fetchone()
        return row

@pytest.fixture
def strict_env(tmp_path):
    """
    TPM=600 (10 tokens/sec) の厳格な環境。
    """
    db_path = tmp_path / "robust.db"
    spot = Spot(name="robust_test", db=str(db_path), tpm=600)
    spot.register_type(CriticalData, code=20, encoder=encode_critical, decoder=decode_critical)
    return spot, db_path

@pytest.mark.asyncio
async def test_strict_rate_limiting(strict_env):
    """
    [Robustness] レートリミッターが理論値通りに動作するか検証する。
    
    Theory:
      TPM=600 -> Rate = 10 tokens/sec
      Task Cost = 5 tokens
      Interval = 5 / 10 = 0.5 sec
      
      10 Tasks:
        Task 0: T=0.0s (即時実行)
        Task 1: T=0.5s
        ...
        Task 9: T=4.5s
      
      Total Elapsed should be >= 4.5s.
      もし 0.5s (前回のテスト) で終わるなら、リミッターは壊れている。
    """
    spot, _ = strict_env
    
    @spot.limiter(cost=5)
    @spot.mark
    async def paced_task(idx: int):
        return idx

    start_time = time.monotonic()
    
    # 並行実行をリクエスト
    tasks = [paced_task(i) for i in range(10)]
    await asyncio.gather(*tasks)
    
    elapsed = time.monotonic() - start_time
    
    print(f"\n[RateLimit] 10 tasks (cost=5, tpm=600) took {elapsed:.4f}s (Theory: ~4.5s)")
    
    # CI環境のゆらぎを許容しつつ、理論的下限(4.5s)を割っていないことを確認
    # ※ 最初の1回はwaitなしなので厳密には (N-1)*Interval
    expected_min_duration = 4.5 
    
    assert elapsed >= expected_min_duration, \
        f"Rate limiter is too loose! Expected at least {expected_min_duration}s, got {elapsed}s"

@pytest.mark.asyncio
async def test_transient_failure_recovery(strict_env):
    """
    [Robustness] 一時的な失敗がDBに永続化されず、再試行で正しく回復・保存されるか検証する。
    """
    spot, db_path = strict_env
    
    # 外部要因による失敗をシミュレートするフラグ
    simulate_network_error = True

    @spot.mark
    async def unstable_task(data: CriticalData) -> str:
        if simulate_network_error and data.id == "bad_item":
            raise RuntimeError("Transient network error")
        return f"Processed {data.id}"

    input_data = CriticalData(id="bad_item", payload=b"\xde\xad\xbe\xef")

    # --- Phase 1: Failure ---
    print("\n[Recovery] Phase 1: Expecting failure...")
    try:
        await unstable_task(input_data)
        pytest.fail("Task should have raised RuntimeError")
    except RuntimeError:
        pass
    
    # 検証1: 失敗したタスクはDBに保存されていてはいけない
    # (beautyspotは成功結果のみをキャッシュすべき)
    counts = inspect_db_counts(str(db_path))
    assert counts["total_records"] == 0, "Failed task was incorrectly persisted to DB!"

    # --- Phase 2: Recovery ---
    print("[Recovery] Phase 2: Retrying after 'recovery'...")
    simulate_network_error = False # 障害復旧
    
    result = await unstable_task(input_data)
    assert result == "Processed bad_item"
    
    # 検証2: 成功後はDBにレコードが1件あるはず
    counts = inspect_db_counts(str(db_path))
    assert counts["total_records"] == 1, "Success result was not persisted!"
    
    # 検証3: DBの内容が正しいか (White-box check)
    # キャッシュキーを計算して直接引くことも可能だが、ここでは件数と中身の存在確認
    # 検証3: DBの内容が正しいか (White-box check)
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT result_data FROM tasks").fetchone()
        # (Msgpackは文字列をそのままUTF-8バイト列として埋め込むため、これで簡易検証可能です)
        assert b"Processed bad_item" in row[0]

@pytest.mark.asyncio
async def test_cache_consistency_verification(strict_env):
    """
    [Robustness] 入力が全く同じなら、キャッシュキーも一意になり、
    DBへの重複書き込みが発生しないことを検証する。
    """
    spot, db_path = strict_env
    
    @spot.mark
    async def deterministic_task(x: int):
        await asyncio.sleep(0.01)
        return x * 2

    # 1回目の実行
    await deterministic_task(42)
    
    # DBの状態を確認
    counts_1 = inspect_db_counts(str(db_path))
    assert counts_1["total_records"] == 1
    
    # 2回目の実行 (キャッシュヒットするはず)
    start = time.monotonic()
    val = await deterministic_task(42)
    elapsed = time.monotonic() - start
    
    assert val == 84
    assert elapsed < 0.01, "Cache hit should be instant"
    
    # DBのレコード数が増えていないことを確認 (重複insertされていないか)
    counts_2 = inspect_db_counts(str(db_path))
    assert counts_2["total_records"] == 1, "Duplicate records found for same input!"

