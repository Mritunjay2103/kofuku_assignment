import hashlib
import threading
from typing import Dict, Optional


class ResponseCache:
    def __init__(self) -> None:
        self._store: Dict[str, dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(text: str, style: str, prompt_version: str) -> str:
        raw = f"{prompt_version}:{style}:{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def get(self, text: str, style: str, prompt_version: str) -> Optional[dict]:
        with self._lock:
            return self._store.get(self._key(text, style, prompt_version))

    def set(self, text: str, style: str, prompt_version: str, value: dict) -> None:
        with self._lock:
            self._store[self._key(text, style, prompt_version)] = value
