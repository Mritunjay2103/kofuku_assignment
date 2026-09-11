import threading
import time
from typing import Dict, Tuple


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._state: Dict[str, Tuple[float, int]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            start, count = self._state.get(key, (now, 0))

            if now - start > self.window:
                start, count = now, 0

            if count >= self.limit:
                return False

            self._state[key] = (start, count + 1)
            return True

    def reset(self) -> None:
        with self._lock:
            self._state.clear()
