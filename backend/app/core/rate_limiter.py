import time
from collections import OrderedDict
from typing import Dict, List
from app.core.exceptions import DomainError


class RateLimitExceededError(DomainError):
    retry_after_seconds: int = 60

    def __init__(self, message: str = "Rate limit exceeded. Please try again later.", retry_after_seconds: int = 60):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class RateLimiter:
    """Sliding-window rate limiter for sensitive authentication & API actions.

    The key space is attacker-controlled (one entry per submitted email address, per
    client address), so the store is bounded and stale keys are evicted. Without
    that, the limiter is itself a memory-exhaustion vector (finding DOS-02).
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60, max_tracked_keys: int = 5_000):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_tracked_keys = max_tracked_keys
        # key -> list of timestamps, ordered by least-recently-touched
        self._records: "OrderedDict[str, List[float]]" = OrderedDict()

    def _evict(self, window_start: float) -> None:
        # First drop anything whose whole window has expired.
        for key in [k for k, stamps in self._records.items() if not stamps or stamps[-1] <= window_start]:
            del self._records[key]

        # Still over budget: discard the least recently used keys. Losing a bucket
        # can only ever cost an attacker's own counter, never a security decision.
        while len(self._records) > self.max_tracked_keys:
            self._records.popitem(last=False)

    def check_rate_limit(self, key: str):
        now = time.time()
        window_start = now - self.window_seconds

        timestamps = self._records.get(key, [])
        # Remove timestamps outside current sliding window
        valid_timestamps = [ts for ts in timestamps if ts > window_start]
        self._records[key] = valid_timestamps
        self._records.move_to_end(key)

        if len(self._records) > self.max_tracked_keys:
            self._evict(window_start)

        if len(valid_timestamps) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - valid_timestamps[0])) + 1
            raise RateLimitExceededError(
                f"Rate limit exceeded. Too many requests. Please try again in {retry_after} seconds.",
                retry_after_seconds=retry_after,
            )

        valid_timestamps.append(now)


rate_limiter = RateLimiter(max_requests=10, window_seconds=60)
