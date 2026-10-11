import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_request_id_is_returned_in_response() -> None:
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/health", headers={"X-Request-ID": "test-request-123"}
        )

    assert response.headers["X-Request-ID"] == "test-request-123"
