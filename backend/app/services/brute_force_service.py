import time
from collections import OrderedDict
from typing import Dict, Optional, Tuple

from app.core.exceptions import AccountLockedError
from app.core.logging import logger


class BruteForceProtectionService:
    """Throttles credential guessing without handing attackers a denial-of-service.

    Two deliberate properties, both of them fixes for finding AUTH-03:

    1. **A lockout blocks failed attempts, not the account owner.** Callers verify
       credentials first and only consult the lockout on failure, so an attacker who
       spams wrong passwords for someone else's address cannot lock that person out.
       Guessing is still stopped: once the threshold is crossed, every further wrong
       password is refused with 423 regardless of how many more are tried.
    2. **The deadline is set once.** Previously every new attempt re-stamped
       ``lockout_until``, so continued attempts extended the lock indefinitely.

    The store is an LRU with a hard cap because its keys are attacker-chosen
    (finding DOS-02). State is still process-local; making it shared across workers
    needs Redis and is tracked separately.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        lockout_duration_seconds: int = 900,
        max_tracked_keys: int = 5_000,
    ):
        self.max_attempts = max_attempts
        self.lockout_duration_seconds = lockout_duration_seconds
        self.max_tracked_keys = max_tracked_keys
        # key -> (failure count, locked_until epoch seconds)
        self._attempts: "OrderedDict[str, Tuple[int, float]]" = OrderedDict()

    # ------------------------------------------------------------------ queries
    def lock_remaining_seconds(self, key: str) -> Optional[int]:
        """Seconds until the lock expires, or None when the key is not locked."""
        entry = self._attempts.get(key)
        if not entry:
            return None

        count, locked_until = entry
        now = time.time()
        if count >= self.max_attempts and now < locked_until:
            return int(locked_until - now) + 1
        if locked_until and now >= locked_until:
            del self._attempts[key]
        return None

    def is_locked(self, key: str) -> bool:
        return self.lock_remaining_seconds(key) is not None

    def check_lockout(self, key: str) -> None:
        """Raise if the key is locked. Call this *after* credentials failed."""
        remaining = self.lock_remaining_seconds(key)
        if remaining is None:
            return

        logger.warning("Blocked brute-force login attempt", key=key)
        raise AccountLockedError(
            "Account temporarily locked out due to repeated failed login attempts. "
            f"Please try again in {int(remaining / 60) + 1} minutes.",
            retry_after_seconds=remaining,
        )

    # ------------------------------------------------------------------ updates
    def record_failed_attempt(self, key: str) -> None:
        now = time.time()
        count, locked_until = self._attempts.get(key, (0, 0.0))
        new_count = count + 1

        # Set the deadline once, when the threshold is first crossed, so further
        # attempts cannot extend the lock.
        if new_count >= self.max_attempts and (not locked_until or now >= locked_until):
            locked_until = now + self.lockout_duration_seconds

        self._attempts[key] = (new_count, locked_until)
        self._attempts.move_to_end(key)
        self._evict()
        logger.warning("Recorded failed login attempt", key=key, total_attempts=new_count)

    def record_successful_login(self, key: str) -> None:
        self._attempts.pop(key, None)

    def _evict(self) -> None:
        now = time.time()
        for key in [
            k for k, (count, until) in self._attempts.items()
            if count < self.max_attempts and until and now >= until
        ]:
            del self._attempts[key]

        while len(self._attempts) > self.max_tracked_keys:
            self._attempts.popitem(last=False)


brute_force_service = BruteForceProtectionService()
