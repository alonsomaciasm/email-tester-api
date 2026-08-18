import hashlib
import os
import pickle
import sys
from typing import Any

from pybloom_live import BloomFilter

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import BLOOM_FILTER_ITEMS, BLOOM_FILTER_MEMORY_BYTES
from app.domain.c_domain_parser import fast_normalize_domain_c
from app.domain.cuckoo_filter import DisposableCuckooFilter

logger = get_logger(__name__)


class DisposableBloomFilter:
    """In-memory Bloom/Cuckoo Filter manager for high-speed disposable domain matching."""

    def __init__(
        self,
        capacity: int = settings.BLOOM_FILTER_EXPECTED_ITEMS,
        error_rate: float = settings.BLOOM_FILTER_ERROR_RATE,
    ) -> None:
        self.capacity = capacity
        self.error_rate = error_rate
        self.bloom: BloomFilter = BloomFilter(capacity=self.capacity, error_rate=self.error_rate)
        self.cuckoo: DisposableCuckooFilter = DisposableCuckooFilter(capacity=self.capacity)
        self._dataset_version: str = "v1.0.0-initial"
        self._dataset_hash: str = ""
        self._raw_domains_count: int = 0

    @staticmethod
    def normalize_domain(domain: str) -> str:
        """Normalizes domain strings using C-accelerated parser or Punycode to prevent homograph evasion attacks."""
        return fast_normalize_domain_c(domain)

    def contains(self, domain: str) -> bool:
        """Checks if normalized domain exists in the active probabilistic filter engine."""
        normalized = self.normalize_domain(domain)
        if settings.BLOOM_OR_CUCKOO_ENGINE == "cuckoo":
            return self.cuckoo.contains(normalized)
        return normalized in self.bloom

    def load_domains(self, domains: set[str] | list[str], version: str = "v1.0.0") -> None:
        """Populates or rebuilds the active filter with a list/set of disposable domains."""
        new_bloom = BloomFilter(capacity=self.capacity, error_rate=self.error_rate)
        new_cuckoo = DisposableCuckooFilter(capacity=self.capacity)

        valid_count = 0
        hasher = hashlib.sha256()

        for d in sorted(domains):
            norm = self.normalize_domain(d)
            if norm:
                new_bloom.add(norm)
                new_cuckoo.add(norm)
                hasher.update(norm.encode("utf-8"))
                valid_count += 1

        self.bloom = new_bloom
        self.cuckoo = new_cuckoo
        self._raw_domains_count = valid_count
        self._dataset_version = version
        self._dataset_hash = hasher.hexdigest()

        BLOOM_FILTER_ITEMS.set(self._raw_domains_count)

        if settings.BLOOM_OR_CUCKOO_ENGINE == "cuckoo":
            mem_size = self.cuckoo.size_in_bytes()
        else:
            try:
                mem_size = sys.getsizeof(self.bloom.bitarray)
            except AttributeError:
                mem_size = sys.getsizeof(self.bloom)

        BLOOM_FILTER_MEMORY_BYTES.set(mem_size)

        logger.info(
            "Probabilistic filter reloaded successfully",
            engine=settings.BLOOM_OR_CUCKOO_ENGINE,
            domains_count=valid_count,
            dataset_version=self._dataset_version,
            dataset_hash=self._dataset_hash[:16],
            memory_bytes=mem_size,
        )

    def save_snapshot(
        self,
        filepath: str = "data/bloom_snapshot.bin",
        sources_status: list[dict[str, Any]] | None = None,
        last_sync_timestamp: str | None = None,
    ) -> bool:
        """Persists binary state snapshot to disk."""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            state = {
                "capacity": self.capacity,
                "error_rate": self.error_rate,
                "bloom": self.bloom,
                "dataset_version": self._dataset_version,
                "dataset_hash": self._dataset_hash,
                "raw_domains_count": self._raw_domains_count,
                "sources_status": sources_status,
                "last_sync_timestamp": last_sync_timestamp,
            }
            with open(filepath, "wb") as f:
                pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
            logger.info("Bloom filter snapshot saved to disk", filepath=filepath, items=self._raw_domains_count)
            return True
        except Exception as e:
            logger.error("Failed to save Bloom filter snapshot to disk", error=str(e))
            return False

    def load_snapshot(self, filepath: str = "data/bloom_snapshot.bin") -> dict[str, Any] | None:
        """Restores binary state snapshot from disk."""
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "rb") as f:
                state = pickle.load(f)
            self.capacity = state["capacity"]
            self.error_rate = state["error_rate"]
            self.bloom = state["bloom"]
            self._dataset_version = state.get("dataset_version", "v1.1.0-snapshot")
            self._dataset_hash = state.get("dataset_hash", "")
            self._raw_domains_count = state.get("raw_domains_count", 0)

            BLOOM_FILTER_ITEMS.set(self._raw_domains_count)
            try:
                mem_size = sys.getsizeof(self.bloom.bitarray)
            except AttributeError:
                mem_size = sys.getsizeof(self.bloom)
            BLOOM_FILTER_MEMORY_BYTES.set(mem_size)

            logger.info("Bloom filter snapshot restored from disk", filepath=filepath, items=self._raw_domains_count)
            return dict(state)
        except Exception as e:
            logger.warning("Failed to load Bloom filter snapshot from disk", error=str(e))
            return None

    def get_info(self) -> dict[str, Any]:
        """Returns metadata regarding filter state for research reproducibility."""
        return {
            "capacity": self.capacity,
            "target_error_rate": self.error_rate,
            "engine": settings.BLOOM_OR_CUCKOO_ENGINE,
            "domain_parser": settings.DOMAIN_PARSER_ENGINE,
            "items_count": self._raw_domains_count,
            "dataset_version": self._dataset_version,
            "dataset_hash": self._dataset_hash,
        }


# Global singleton instance
bloom_filter_service = DisposableBloomFilter()
