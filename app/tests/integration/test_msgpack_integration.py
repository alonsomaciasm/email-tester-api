import msgpack
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
@pytest.mark.integration
async def test_msgpack_single_email_verification() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/v1/verify-email",
            json={"email": "testuser@gmail.com"},
            headers={"Accept": "application/x-msgpack"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-msgpack"

        # Unpack binary MessagePack payload
        unpacked = msgpack.unpackb(response.content, raw=False)
        assert isinstance(unpacked, dict)
        assert "disposable" in unpacked
        assert "confidence" in unpacked
        assert "risk_score" in unpacked
        assert unpacked["disposable"] is False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_msgpack_batch_email_verification() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/v1/verify-batch",
            json={"emails": ["user1@mailinator.com", "user2@gmail.com"]},
            headers={"Accept": "application/x-msgpack"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-msgpack"

        unpacked = msgpack.unpackb(response.content, raw=False)
        assert isinstance(unpacked, dict)
        assert unpacked["total_processed"] == 2
        assert len(unpacked["results"]) == 2
        assert unpacked["results"][0]["disposable"] is True
