import pytest
from httpx import ASGITransport, AsyncClient

from app.infra.dataset_sync_job import dataset_sync_job
from app.main import app


@pytest.fixture(autouse=True)
def setup_seed_dataset() -> None:
    dataset_sync_job.initialize_seed()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_healthz_and_readyz_probes() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res_health = await ac.get("/healthz")
        assert res_health.status_code == 200
        assert res_health.json() == {"status": "ok"}

        res_detailed = await ac.get("/healthz/detailed")
        assert res_detailed.status_code in (200, 503)
        detailed_data = res_detailed.json()
        assert "l1_memory_cache" in detailed_data
        assert "redis" in detailed_data
        assert "dns_circuit_breaker" in detailed_data

        res_dataset = await ac.get("/internal/dataset-info")
        assert res_dataset.status_code == 200
        data = res_dataset.json()
        assert "capacity" in data
        assert "items_count" in data
        assert "dataset_hash" in data


@pytest.mark.asyncio
@pytest.mark.integration
async def test_verify_email_known_disposable() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/v1/verify-email",
            json={"email": "victim@mailinator.com"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["disposable"] is True
        assert body["confidence"] == "high"
        assert body["reason"] == "known_provider"
        assert body["risk_score"] == 100
        assert "request_id" in body

        # Crucial Privacy Contract: Response MUST NOT contain the email or domain string
        response_text = response.text
        assert "victim" not in response_text
        assert "mailinator.com" not in response_text


@pytest.mark.asyncio
@pytest.mark.integration
async def test_verify_email_typo_detection() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/v1/verify-email",
            json={"email": "john@gmai.com"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["did_you_mean"] == "gmail.com"
        assert body["risk_score"] > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_verify_email_batch() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/v1/verify-batch",
            json={"emails": ["user1@mailinator.com", "user2@gmail.com", "user3@gmai.com"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total_processed"] == 3
        assert len(body["results"]) == 3
        assert body["results"][0]["disposable"] is True
        assert body["results"][2]["did_you_mean"] == "gmail.com"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_verify_email_invalid_format_privacy() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        invalid_email = "not-an-email-address-string"
        response = await ac.post(
            "/v1/verify-email",
            json={"email": invalid_email},
        )
        assert response.status_code == 422
        # Verify invalid email string is NOT echoed back in error response
        assert invalid_email not in response.text


@pytest.mark.asyncio
@pytest.mark.integration
async def test_security_headers_present() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/healthz")
        headers = response.headers
        assert "Strict-Transport-Security" in headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert "server" not in headers
        assert "Server" not in headers


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dashboard_ui() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/dashboard")
        assert response.status_code == 200
        assert "Cyber Glassmorphism" in response.text
