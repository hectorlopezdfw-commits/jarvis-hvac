from __future__ import annotations

import threading
import time


class SlidingWindowRateLimiter:
    """In-memory per-key limit. One process, resets when the process restarts."""

    def __init__(self, max_hits: int, window_seconds: float) -> None:
        self.max_hits = max_hits
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def allow(self, key: str, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        cutoff = moment - self.window_seconds
        with self._lock:
            recent = [hit for hit in self._hits.get(key, []) if hit > cutoff]
            if len(recent) >= self.max_hits:
                self._hits[key] = recent
                self._prune_unlocked()
                return False
            recent.append(moment)
            self._hits[key] = recent
            self._prune_unlocked()
            return True

    def _prune_unlocked(self) -> None:
        if len(self._hits) <= 4096:
            return
        # Drop the keys that have been quiet the longest. The lock is already held.
        ranked = sorted(self._hits.items(), key=lambda item: item[1][-1] if item[1] else 0)
        for key, _hits in ranked[: len(self._hits) - 2048]:
            self._hits.pop(key, None)
