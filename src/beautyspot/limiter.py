# src/beautyspot/limiter.py

import time
import asyncio
import threading


class TokenBucket:
    """
    A smooth rate limiter based on the GCRA (Generic Cell Rate Algorithm).

    Features:
    - No burst after long idle (Strict Pacing).
    - No start-up delay for the very first request.
    - Fails fast if a task cost exceeds the TPM limit.
    - Thread-safe and Async-compatible.
    - Uses monotonic clock.
    """

    def __init__(self, tokens_per_minute: int):
        if tokens_per_minute <= 0:
            raise ValueError("tokens_per_minute must be positive")

        # Rate: tokens per second
        self.rate = float(tokens_per_minute) / 60.0

        # Maximum allowed cost per task.
        # A single task consuming more than the TPM limit is physically impossible
        # to process within the rate window, so it should be forbidden.
        self.max_cost = int(tokens_per_minute)

        # Theoretical Arrival Time (TAT)
        self.tat = time.monotonic()
        self.lock = threading.Lock()

    def _consume_reservation(self, cost: int) -> float:
        """
        Calculates wait time and updates TAT.
        Returns seconds to wait.
        """
        if cost <= 0:
            return 0.0

        # Guard: Prevent requests that exceed the rate limit capacity entirely
        if cost > self.max_cost:
            raise ValueError(
                f"Requested cost ({cost}) exceeds the maximum limit of {self.max_cost} tokens per minute. "
                "This task cannot be processed within the defined rate limit."
            )

        now = time.monotonic()
        increment = cost / self.rate

        with self.lock:
            if now > self.tat:
                self.tat = now

            wait_time = self.tat - now
            if wait_time < 0:
                wait_time = 0.0

            self.tat += increment

            return wait_time

    def consume(self, cost: int):
        """Sync version: blocks thread until rate limit allows"""
        wait_time = self._consume_reservation(cost)
        if wait_time > 0:
            time.sleep(wait_time)

    async def consume_async(self, cost: int):
        """Async version: non-blocking await"""
        wait_time = self._consume_reservation(cost)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
