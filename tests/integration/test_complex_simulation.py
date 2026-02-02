# tests/integration/test_complex_simulation.py

import pytest
import asyncio
import time
from dataclasses import dataclass
from beautyspot import Spot

# --- Custom Data Structure ---
@dataclass
class Complexity:
    """テスト用のカスタムデータ構造"""
    id: str
    score: float
    meta: dict

    # 比較用に実装
    def __eq__(self, other):
        if not isinstance(other, Complexity):
            return NotImplemented
        return self.id == other.id and abs(self.score - other.score) < 1e-6

# --- Encoder/Decoder for Custom Data ---
def encode_complexity(obj: Complexity) -> list:
    return [obj.id, obj.score, obj.meta]

def decode_complexity(data: list) -> Complexity:
    return Complexity(id=data[0], score=data[1], meta=data[2])


@pytest.fixture
def chaos_env(tmp_path):
    """
    複雑な条件を設定したSpot環境。
    TPMを低く設定し、レート制限の効果を見やすくする。
    """
    db_path = tmp_path / "chaos.db"
    
    # TPM=600 (10 tokens/sec)
    # 並行でバーストするとすぐに待機が発生する設定
    spot = Spot(name="chaos_test", db=str(db_path), tpm=600)
    
    # カスタム型の登録
    spot.register_type(Complexity, code=10, encoder=encode_complexity, decoder=decode_complexity)
    
    return spot

@pytest.mark.asyncio
async def test_resilient_pipeline_simulation(chaos_env):
    """
    並行実行、レート制限、部分的失敗を含む複雑なパイプラインのシミュレーション。
    """
    spot = chaos_env
    
    # 実行追跡用
    stats = {
        "process_runs": 0,
        "failures": 0
    }
    
    # 失敗をシミュレートするためのフラグ (特定IDの初回のみ失敗)
    flake_target_id = "item_5"
    has_failed_once = False

    # --- Task Definitions ---

    @spot.mark
    def ingest_data(n: int) -> list[Complexity]:
        """データを生成するタスク"""
        return [
            Complexity(id=f"item_{i}", score=0.1 * i, meta={"tag": "test"}) 
            for i in range(n)
        ]

    @spot.limiter(cost=5)  # 1回の実行で5トークン消費 (秒間2回までしか走れない)
    @spot.mark(save_blob=True) # Blobストレージも併用
    async def process_item(item: Complexity) -> Complexity:
        nonlocal has_failed_once
        
        # 実行回数をカウント
        stats["process_runs"] += 1
        
        # 特定のアイテムで、初回のみ意図的に失敗させる
        if item.id == flake_target_id and not has_failed_once:
            stats["failures"] += 1
            has_failed_once = True
            raise RuntimeError(f"Simulated crash for {item.id}")

        # 重い処理をシミュレート
        await asyncio.sleep(0.01)
        
        # スコアを更新
        item.score *= 2.0
        item.meta["processed"] = True
        return item

    # --- Phase 1: Ingest & First Parallel Execution (With Failure) ---
    print("\n[Phase 1] Starting parallel processing (expecting 1 failure)...")
    
    raw_items = ingest_data(10) # 0..9
    
    # item_5 は失敗するはず
    tasks = [process_item(item) for item in raw_items]
    results_ph1 = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 結果の検証
    success_count = sum(1 for r in results_ph1 if not isinstance(r, Exception))
    exception_count = sum(1 for r in results_ph1 if isinstance(r, Exception))
    
    assert success_count == 9
    assert exception_count == 1
    assert isinstance(results_ph1[5], RuntimeError) # item_5
    
    # 実行統計: 全員走ったはず
    assert stats["process_runs"] == 10

    # --- Phase 2: Retry (Recovery) ---
    print("\n[Phase 2] Retrying pipeline (expecting recovery)...")
    
    # 再度 ingest_data を呼んで「初期状態の入力」を取得しなおします。
    # ingest_data もキャッシュされているため、DBから初期データが復元されます。
    raw_items_retry = ingest_data(10)
    
    # item_0..4, 6..9 は初期状態の入力ならキャッシュヒットするはず
    # item_5 は前回失敗してキャッシュがないので、再実行されるはず
    
    tasks_retry = [process_item(item) for item in raw_items_retry]
    results_ph2 = await asyncio.gather(*tasks_retry, return_exceptions=False) # 今度は例外なし
    
    
    # 結果検証
    assert len(results_ph2) == 10
    assert results_ph2[5].id == "item_5"
    assert results_ph2[5].score == 1.0 # 0.5 * 2.0
    
    # 統計検証
    # process_runs は Phase1(10回) + Phase2(1回: item_5のみ) = 11回
    assert stats["process_runs"] == 11, "キャッシュ済みのタスクが再実行されてしまっています"
    
    print("✓ Partial recovery confirmed.")

    # --- Phase 3: Rate Limiting Stress Test ---
    print("\n[Phase 3] Stress testing rate limiter...")
    
    # 大量のリクエストを同時に投げる
    # TPM=600, cost=5 -> 120 calls/min = 2 calls/sec
    # 10個投げると理論上5秒かかるはず
    
    # キャッシュを無効化するためにバージョンを変える
    @spot.limiter(cost=5)
    @spot.mark(version="stress_test")
    async def heavy_task(x):
        return x * 2

    start_time = time.monotonic()
    
    stress_tasks = [heavy_task(i) for i in range(10)]
    await asyncio.gather(*stress_tasks)
    
    elapsed = time.monotonic() - start_time
    print(f"Elapsed time for 10 limited tasks: {elapsed:.2f}s")
    
    # 少なくとも少しは待たされているはず (並列実行だがレート制限で直列化に近い挙動になる)
    # 完全に並列なら 0.0s 近いが、制限により数秒かかる
    assert elapsed > 0.4, "レートリミットが効いていないようです"

