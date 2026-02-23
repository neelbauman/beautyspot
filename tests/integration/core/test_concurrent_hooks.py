# tests/integration/core/test_concurrent_hooks.py

"""ThreadSafeHookBase の並行呼び出しテスト。"""

import threading
from beautyspot.hooks import ThreadSafeHookBase, HookBase
from beautyspot.types import PreExecuteContext
import beautyspot as bs
from beautyspot.db import SQLiteTaskDB


class CounterHook(ThreadSafeHookBase):
    """スレッドセーフなカウンタフック。"""

    def __init__(self):
        super().__init__()
        self.pre_count = 0
        self.hit_count = 0
        self.miss_count = 0

    def pre_execute(self, context):
        self.pre_count += 1

    def on_cache_hit(self, context):
        self.hit_count += 1

    def on_cache_miss(self, context):
        self.miss_count += 1


def test_threadsafe_hook_concurrent_calls():
    """複数スレッドから ThreadSafeHookBase を呼んでもカウンタが正確であることを確認する。"""
    hook = CounterHook()
    num_threads = 10
    calls_per_thread = 100

    def call_hooks():
        for _ in range(calls_per_thread):
            ctx = PreExecuteContext(
                func_name="f", input_id="id", cache_key="ck",
                args=(), kwargs={},
            )
            hook.pre_execute(ctx)

    threads = [threading.Thread(target=call_hooks) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert hook.pre_count == num_threads * calls_per_thread


def test_threadsafe_hook_with_spot(tmp_path):
    """ThreadSafeHookBase が Spot 統合で正しく動作することを確認する。"""
    hook = CounterHook()
    spot = bs.Spot(
        name="hook_test",
        db=SQLiteTaskDB(tmp_path / "h.db"),
        storage_backend=bs.LocalStorage(tmp_path / "blobs"),
    )

    @spot.mark(hooks=[hook])
    def compute(x):
        return x * 2

    # 1回目: cache miss
    assert compute(5) == 10
    assert hook.pre_count == 1
    assert hook.miss_count == 1
    assert hook.hit_count == 0

    # 2回目: cache hit
    assert compute(5) == 10
    assert hook.pre_count == 2
    assert hook.miss_count == 1
    assert hook.hit_count == 1


def test_threadsafe_hook_inherits_hookbase():
    """ThreadSafeHookBase が HookBase のサブクラスであることを確認する。"""
    hook = CounterHook()
    assert isinstance(hook, HookBase)
    assert isinstance(hook, ThreadSafeHookBase)
