import pytest

from app.core.config import settings
from app.domain.bloom_filter import DisposableBloomFilter, bloom_filter_service
from app.domain.c_domain_parser import fast_normalize_domain_c
from app.domain.cuckoo_filter import DisposableCuckooFilter


def test_cuckoo_filter_basic_operations() -> None:
    cuckoo = DisposableCuckooFilter(capacity=1000)
    test_domains = ["mailinator.com", "10minutemail.com", "guerrillamail.com"]

    for d in test_domains:
        inserted = cuckoo.add(d)
        assert inserted is True

    for d in test_domains:
        assert cuckoo.contains(d) is True

    assert cuckoo.contains("gmail.com") is False

    # Test dynamic deletion
    removed = cuckoo.remove("10minutemail.com")
    assert removed is True
    assert cuckoo.contains("10minutemail.com") is False
    assert cuckoo.contains("mailinator.com") is True


def test_fast_normalize_domain_c_parity() -> None:
    raw_emails = [
        "  User@Gmail.COM  ",
        "john.doe@MAILINATOR.COM",
        "  admin@GMAıL.com ",  # Turkish dotless i (homograph punycode test)
    ]

    for raw in raw_emails:
        norm_c = fast_normalize_domain_c(raw)
        norm_orig = DisposableBloomFilter.normalize_domain(raw)
        assert norm_c == norm_orig


def test_probabilistic_filter_engine_switching() -> None:
    test_domains = {"mailinator.com", "tempmail.org"}
    bloom_filter_service.load_domains(test_domains, version="v-test")

    # Test Bloom filter mode
    settings.BLOOM_OR_CUCKOO_ENGINE = "bloom"
    assert bloom_filter_service.contains("mailinator.com") is True
    assert bloom_filter_service.contains("gmail.com") is False

    # Test Cuckoo filter mode
    settings.BLOOM_OR_CUCKOO_ENGINE = "cuckoo"
    assert bloom_filter_service.contains("mailinator.com") is True
    assert bloom_filter_service.contains("gmail.com") is False

    # Restore default
    settings.BLOOM_OR_CUCKOO_ENGINE = "bloom"
