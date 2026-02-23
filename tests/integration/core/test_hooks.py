import time
from beautyspot.core import Spot
from beautyspot.hooks import HookBase

class MockTokenMetricsHook(HookBase):
    def __init__(self):
        self.total_saved_tokens = 0
        self.total_consumed_tokens = 0
        self.execution_times = []
        self._start_time = 0

    def pre_execute(self, context):
        # 実行前に時間を記録（状態の保持テスト）
        self._start_time = time.time()

    def on_cache_hit(self, context):
        # ヒット時は戻り値の長さ（仮のトークン数）を節約分として加算
        self.total_saved_tokens += len(context.result)

    def on_cache_miss(self, context):
        # ミス時は実際の消費分として加算し、実行時間も記録
        self.total_consumed_tokens += len(context.result)
        self.execution_times.append(time.time() - self._start_time)

def test_hook_lifecycle(spot: Spot):
    metrics = MockTokenMetricsHook()

    @spot.mark(hooks=[metrics])
    def fetch_data(query: str) -> str:
        time.sleep(0.1) # 実行時間のシミュレーション
        return f"Result for {query}"

    # 1回目 (Cache Miss)
    res1 = fetch_data("A")
    assert metrics.total_consumed_tokens == len(res1)
    assert metrics.total_saved_tokens == 0
    assert len(metrics.execution_times) == 1
    assert metrics.execution_times[0] >= 0.1

    # 2回目 (Cache Hit)
    res2 = fetch_data("A")
    assert metrics.total_saved_tokens == len(res2)
    # 消費トークンは増えていないことを確認
    assert metrics.total_consumed_tokens == len(res1) 
    # 実行回数(ミス回数)は増えていない
    assert len(metrics.execution_times) == 1

