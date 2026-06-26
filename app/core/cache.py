import hashlib
import time
from typing import Any, Optional


class SimpleCache:
    def __init__(self, ttl: int = 300):
        self._store: dict = {}
        self._ttl = ttl

    def _key(self, prompt: str) -> str:
        return hashlib.md5(prompt.encode("utf-8")).hexdigest()

    def get(self, prompt: str) -> Optional[Any]:
        k = self._key(prompt)
        entry = self._store.get(k)
        if entry and time.time() - entry["ts"] < self._ttl:
            return entry["value"]
        if entry:
            del self._store[k]
        return None

    def set(self, prompt: str, value: Any) -> None:
        self._store[self._key(prompt)] = {"value": value, "ts": time.time()}


llm_cache = SimpleCache(ttl=300)
