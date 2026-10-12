import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_metrics_tracks_requests_and_request_ids_are_returned() -> None:
    from app.main import create_app

    app = create_app(model_loader=object)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        health = await client.get("/health", headers={"X-Request-ID": "cv-test-123"})
        metrics = await client.get("/metrics")

    assert health.headers["x-request-id"] == "cv-test-123"
    assert metrics.status_code == 200
    assert metrics.json()["requests_total"] == 2
    assert metrics.json()["model_ready"] is True
