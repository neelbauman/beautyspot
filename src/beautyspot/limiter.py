# src/beautyspot/limiter.py

import time
import asyncio
import threading


class TokenBucket:
    def __init__(self, tokens_per_minute: int):
        self.capacity = 0
        self.tokens = float(tokens_per_minute)
        self.last_refill = time.time()
        self.lock = threading.Lock()

    def _refill(self):
        now = time.time()
        delta = now -self.last_refill
        refill_amount = delta * (self.capacity / 60.0)
        self.tokens = min(self.capacity, self.tokens + refill_amount)
        self.last_refill = now

    def _calculate_wait(self, cost: int) -> float:
        if cost <= 0: return 0.0

        needed = cost - self.tokens
        if needed <= 0:
            self.tokens -= cost
            return 0.0
        else:
            rate = self.capacity / 60.0
            wait_time = needed / rate
            return wait_time

    def consume(self, cost: int):
        """Sync version: blocks thread"""
        if cost <= 0: return
        while True:
            with self.lock:
                self._refill()
                wait_time = self._calculate_wait(cost)
                if wait_time <= 0:
                    return
            
            # ロックを解放して待機
            time.sleep(wait_time + 0.01)

    async def consume_async(self, cost: int):
        """Async version: non-blocking await"""
        if cost <= 0: return
        while True:
            # スレッドロックは非同期でも必要（変数は共有されているため）
            with self.lock:
                self._refill()
                wait_time = self._calculate_wait(cost)
                if wait_time <= 0:
                    return
            
            # イベントループをブロックせずに待機
            await asyncio.sleep(wait_time + 0.01)

