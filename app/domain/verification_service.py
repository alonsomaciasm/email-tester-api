import asyncio
import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import (
    BLOOM_FILTER_LOOKUPS,
    VERIFICATION_LATENCY_SECONDS,
    VERIFICATION_REQUESTS_TOTAL,
)
from app.domain.bloom_filter import DisposableBloomFilter, bloom_filter_service
from app.domain.heuristics import heuristics_engine
from app.domain.mx_resolver import async_mx_resolver, identify_mx_provider, is_null_mx
from app.infra.l1_cache import l1_cache
from app.infra.redis_client import redis_manager

logger = get_logger(__name__)


class VerificationResult(BaseModel):
    disposable: bool
    confidence: Literal["high", "medium", "low"]
    reason: Literal["known_provider", "no_mx", "heuristic", "clean"]
    risk_score: int = Field(default=0, ge=0, le=100, description="Risk score from 0 (safe) to 100 (disposable)")
    mx_provider: str | None = Field(default=None, description="Identified infrastructure MX provider")
    did_you_mean: str | None = Field(default=None, description="Suggested legitimate domain typo fix if detected")
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timing_ms: dict[str, float] = Field(default_factory=dict)


class VerificationService:
    def __init__(self) -> None:
        self.whitelist: set[str] = self._load_whitelisted_domains()

    def _load_whitelisted_domains(self) -> set[str]:
        """Loads domain whitelist from .env settings and local config/whitelist.txt file."""
        import os

        whitelisted: set[str] = {DisposableBloomFilter.normalize_domain(d) for d in settings.WHITELISTED_DOMAINS if d}

        file_path = settings.WHITELIST_FILE_PATH
        if os.path.exists(file_path):
            try:
                with open(file_path, encoding="utf-8") as f:
                    for line in f:
                        clean = line.strip().lower()
                        if clean and not clean.startswith("#") and not clean.startswith("//"):
                            whitelisted.add(DisposableBloomFilter.normalize_domain(clean))
                logger.info("Local domain whitelist file loaded", file_path=file_path, items=len(whitelisted))
            except Exception as e:
                logger.warning("Failed to load whitelist file", file_path=file_path, error=str(e))

        return whitelisted

    async def verify_email_domain(
        self,
        email_str: str,
        request_id: str | None = None,
    ) -> VerificationResult:
        """Processes verification cascading pipeline.

        CRITICAL PRIVACY RULE: The local-part is discarded immediately after extracting the domain.
        No function logs, stores, or propagates the raw email string.
        """
        start_total = time.perf_counter()
        req_id = request_id or str(uuid.uuid4())
        timing: dict[str, float] = {}

        # 1. Extract domain & normalize IDNA
        try:
            _, domain_raw = email_str.rsplit("@", 1)
        except ValueError:
            domain_raw = email_str

        domain = DisposableBloomFilter.normalize_domain(domain_raw)

        # Check L1 In-Memory LRU Cache first for sub-millisecond responses
        cached_result = l1_cache.get(domain)
        if cached_result is not None:
            # Re-assign fresh request_id
            cloned = cached_result.model_copy(update={"request_id": req_id})
            cloned.timing_ms = {"l1_cache_hit_ms": 0.05, "total_ms": round((time.perf_counter() - start_total) * 1000, 3)}
            return cloned

        # Tier 0: Check explicit domain whitelist (env + whitelist.txt)
        if domain in self.whitelist:
            res = VerificationResult(
                disposable=False,
                confidence="high",
                reason="clean",
                risk_score=0,
                mx_provider="Whitelisted Domain",
                did_you_mean=None,
                request_id=req_id,
                timing_ms={"whitelist_ms": 0.01},
            )
            l1_cache.set(domain, res)
            self._audit_log(req_id, domain, res, start_total)
            return res

        # Check Typo suggestion
        did_you_mean = heuristics_engine.detect_typo(domain)

        # 2. Tier 1: Local In-Memory Bloom Filter (~50ms target)
        t0 = time.perf_counter()
        is_bloom_hit = bloom_filter_service.contains(domain)
        bloom_duration = (time.perf_counter() - t0) * 1000
        timing["bloom_ms"] = round(bloom_duration, 3)
        VERIFICATION_LATENCY_SECONDS.labels(tier="bloom").observe(bloom_duration / 1000)

        if is_bloom_hit:
            BLOOM_FILTER_LOOKUPS.labels(result="hit").inc()
            res = VerificationResult(
                disposable=True,
                confidence="high",
                reason="known_provider",
                risk_score=100,
                mx_provider="Disposable Domain List",
                did_you_mean=did_you_mean,
                request_id=req_id,
                timing_ms=timing,
            )
            l1_cache.set(domain, res)
            self._audit_log(req_id, domain, res, start_total)
            return res

        BLOOM_FILTER_LOOKUPS.labels(result="miss").inc()

        # 3. Tier 2: Redis MX Cache Lookup
        t0 = time.perf_counter()
        cached_mx = await redis_manager.get_cached_mx(domain)
        redis_duration = (time.perf_counter() - t0) * 1000
        timing["redis_ms"] = round(redis_duration, 3)
        VERIFICATION_LATENCY_SECONDS.labels(tier="redis").observe(redis_duration / 1000)

        mx_records = cached_mx

        # 4. Tier 3: Async DNS MX Lookup (if cache miss)
        if mx_records is None:
            t0 = time.perf_counter()
            mx_records = await async_mx_resolver.resolve_mx(domain)
            dns_duration = (time.perf_counter() - t0) * 1000
            timing["dns_ms"] = round(dns_duration, 3)
            VERIFICATION_LATENCY_SECONDS.labels(tier="dns").observe(dns_duration / 1000)

            # Store in Redis cache if resolved successfully
            await redis_manager.set_cached_mx(domain, mx_records)

        mx_provider = identify_mx_provider(mx_records)
        has_null_mx = is_null_mx(mx_records)

        # Evaluate MX Presence or Null MX (RFC 7508)
        if not mx_records or has_null_mx:
            risk = heuristics_engine.compute_risk_score(
                disposable=True,
                reason="no_mx",
                confidence="high",
                mx_provider=mx_provider,
                did_you_mean=did_you_mean,
            )
            res = VerificationResult(
                disposable=True,
                confidence="high",
                reason="no_mx",
                risk_score=risk,
                mx_provider=mx_provider or "No MX Record",
                did_you_mean=did_you_mean,
                request_id=req_id,
                timing_ms=timing,
            )
            l1_cache.set(domain, res)
            self._audit_log(req_id, domain, res, start_total)
            return res

        # 5. Tier 4: Heuristics Evaluation
        t0 = time.perf_counter()
        is_heuristic_disposable, heuristic_detail = heuristics_engine.evaluate_domain(domain, mx_records)
        heuristics_duration = (time.perf_counter() - t0) * 1000
        timing["heuristics_ms"] = round(heuristics_duration, 3)
        VERIFICATION_LATENCY_SECONDS.labels(tier="heuristics").observe(heuristics_duration / 1000)

        if is_heuristic_disposable:
            reason_str = "heuristic"
            risk = heuristics_engine.compute_risk_score(
                disposable=True,
                reason=reason_str,
                confidence="medium",
                mx_provider=mx_provider,
                did_you_mean=did_you_mean,
            )
            res = VerificationResult(
                disposable=True,
                confidence="medium",
                reason="heuristic",
                risk_score=risk,
                mx_provider=mx_provider,
                did_you_mean=did_you_mean,
                request_id=req_id,
                timing_ms=timing,
            )
        else:
            risk = heuristics_engine.compute_risk_score(
                disposable=False,
                reason="clean",
                confidence="high",
                mx_provider=mx_provider,
                did_you_mean=did_you_mean,
            )
            res = VerificationResult(
                disposable=False,
                confidence="high",
                reason="clean",
                risk_score=risk,
                mx_provider=mx_provider,
                did_you_mean=did_you_mean,
                request_id=req_id,
                timing_ms=timing,
            )

        l1_cache.set(domain, res)
        self._audit_log(req_id, domain, res, start_total)
        return res

    async def verify_email_batch(
        self,
        emails: list[str],
        max_concurrency: int = 20,
    ) -> list[VerificationResult]:
        """Concurrently verifies a batch of emails with bounded parallelism."""
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _worker(email: str) -> VerificationResult:
            async with semaphore:
                return await self.verify_email_domain(email)

        tasks = [_worker(email) for email in emails]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)

    def _audit_log(
        self,
        request_id: str,
        domain: str,
        result: VerificationResult,
        start_time: float,
    ) -> None:
        total_duration_ms = round((time.perf_counter() - start_time) * 1000, 3)
        result.timing_ms["total_ms"] = total_duration_ms

        VERIFICATION_REQUESTS_TOTAL.labels(
            disposable=str(result.disposable),
            confidence=result.confidence,
            reason=result.reason,
        ).inc()

        logger.info(
            "Security audit email verification event",
            event_type="audit.email_verification",
            security_action="BLOCKED" if result.disposable else "ALLOWED",
            request_id=request_id,
            domain=domain,
            disposable=result.disposable,
            confidence=result.confidence,
            reason=result.reason,
            risk_score=result.risk_score,
            mx_provider=result.mx_provider,
            did_you_mean=result.did_you_mean,
            duration_ms=total_duration_ms,
        )


verification_service = VerificationService()
