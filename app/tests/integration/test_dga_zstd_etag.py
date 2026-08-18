import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.dga_detector import dga_detector
from app.main import app


def test_dga_entropy_detector_unit() -> None:
    # High entropy / stochastic synthetic domains -> DGA
    is_dga, entropy = dga_detector.is_dga_domain("x89a1zk9q2b881.biz")
    assert is_dga is True
    assert entropy > 3.0

    # Clean / legitimate low entropy domains -> Not DGA
    is_dga_clean, entropy_clean = dga_detector.is_dga_domain("company.com")
    assert is_dga_clean is False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_etag_304_caching_behavior() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        req_headers = {"X-Request-ID": "test-static-request-123"}

        # First request -> gets ETag header
        resp1 = await ac.post("/v1/verify-email", json={"email": "etaguser@gmail.com"}, headers=req_headers)
        assert resp1.status_code == 200
        assert "etag" in resp1.headers
        etag = resp1.headers["etag"]

        # Second request with If-None-Match -> gets HTTP 304 Not Modified
        req_headers["If-None-Match"] = etag
        resp2 = await ac.post("/v1/verify-email", json={"email": "etaguser@gmail.com"}, headers=req_headers)
        assert resp2.status_code == 304
        assert resp2.content == b""


@pytest.mark.asyncio
@pytest.mark.integration
async def test_zstd_compression_behavior() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Large batch of 50 emails to exceed minimum size compression threshold
        emails_batch = [f"zstd_user_{i}@gmail.com" for i in range(50)]
        response = await ac.post(
            "/v1/verify-batch",
            json={"emails": emails_batch},
            headers={"Accept-Encoding": "zstd"},
        )
        assert response.status_code == 200
        assert response.headers.get("content-encoding") == "zstd"

        # HTTPX client transparently decompresses 'zstd' response content
        assert b"total_processed" in response.content
