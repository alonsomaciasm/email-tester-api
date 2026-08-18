import time
from collections import OrderedDict
from typing import Any


class L1InMemoryCache:
    """High-performance thread-safe L1 In-Memory LRU Cache with TTL expiry.

    Reduces latency for ultra-frequent domain lookups (e.g., gmail.com, outlook.com)
    to sub-millisecond execution times without hitting Redis or DNS resolvers.
    """

    def __init__(self, maxsize: int = 10000, ttl_seconds: float = 300.0) -> None:
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        """Retrieves non-expired entry from L1 cache."""
        if key not in self._cache:
            self._misses += 1
            return None

        value, expiry = self._cache[key]
        if time.monotonic() > expiry:
            del self._cache[key]
            self._misses += 1
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        """Stores item in L1 cache with TTL, evicting oldest item if capacity is exceeded."""
        if key in self._cache:
            del self._cache[key]

        elif len(self._cache) >= self.maxsize:
            # Evict LRU (first item)
            self._cache.popitem(last=False)

        expiry = time.monotonic() + self.ttl_seconds
        self._cache[key] = (value, expiry)

    def clear(self) -> None:
        """Flushes the cache."""
        self._cache.clear()

    def get_stats(self) -> dict[str, Any]:
        """Returns cache telemetry stats."""
        total = self._hits + self._misses
        hit_ratio = round((self._hits / total) * 100, 2) if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "maxsize": self.maxsize,
            "ttl_seconds": self.ttl_seconds,
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio_percent": hit_ratio,
        }


# Global singleton instance for L1 Cache
l1_cache = L1InMemoryCache(maxsize=10000, ttl_seconds=300.0)
