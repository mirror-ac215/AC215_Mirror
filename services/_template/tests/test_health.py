import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_health_returns_ok_status() -> None:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
