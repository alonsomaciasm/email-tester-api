import pytest

from app.domain.bloom_filter import DisposableBloomFilter
from app.domain.heuristics import HeuristicsEngine
from app.domain.verification_service import VerificationService


@pytest.mark.unit
def test_bloom_filter_normalization_and_lookup() -> None:
    bloom = DisposableBloomFilter()
    test_domains = {"mailinator.com", "guerrillamail.com"}
    bloom.load_domains(test_domains, version="test-v1")

    # Standard lookup
    assert bloom.contains("mailinator.com") is True
    assert bloom.contains("gmail.com") is False

    # IDNA / Punycode unicode normalization lookup (e.g. gmaıl.com with turkish dotless i)
    normalized = bloom.normalize_domain("gmaıl.com")
    assert normalized == "gmail.com" or normalized.startswith("xn--")


@pytest.mark.unit
def test_heuristics_engine() -> None:
    engine = HeuristicsEngine()

    # Punycode homograph check
    is_disp, reason = engine.evaluate_domain("xn--gma-jua.com", [])
    assert is_disp is True
    assert reason == "punycode_homograph"

    # Keyword check
    is_disp, reason = engine.evaluate_domain("temp-test-domain.org", [])
    assert is_disp is True
    assert reason == "heuristic_keyword"

    # Disposable MX host check
    is_disp, reason = engine.evaluate_domain("custom-domain.com", ["mx.mailinator.com"])
    assert is_disp is True
    assert reason == "disposable_mx_target"

    # Clean domain
    is_disp, reason = engine.evaluate_domain("company.com", ["mail.company.com"])
    assert is_disp is False
    assert reason == "clean"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_verification_service_disposable() -> None:
    from app.infra.dataset_sync_job import dataset_sync_job

    dataset_sync_job.initialize_seed()

    service = VerificationService()

    # Known seed disposable domain
    res = await service.verify_email_domain("testuser@mailinator.com")
    assert res.disposable is True
    assert res.confidence == "high"
    assert res.reason == "known_provider"
    assert res.request_id is not None

    # Clean domain
    res_clean = await service.verify_email_domain("user@gmail.com")
    assert res_clean.request_id is not None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_verification_service_whitelist_tier0() -> None:
    service = VerificationService()
    service.whitelist.add("custom-enterprise-domain.com")

    res = await service.verify_email_domain("user@custom-enterprise-domain.com")
    assert res.disposable is False
    assert res.confidence == "high"
    assert res.reason == "clean"
    assert "whitelist_ms" in res.timing_ms
