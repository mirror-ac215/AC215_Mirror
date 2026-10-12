import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_health_reports_unready_before_a_model_is_loaded() -> None:
    from app.main import create_app

    app = create_app(model_loader=lambda: None)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unready",
        "model_version": "cv-vit-b16-v3",
    }


@pytest.mark.anyio
async def test_health_reports_model_version_after_a_model_is_loaded() -> None:
    from app.main import create_app

    app = create_app(model_loader=object)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "model_version": "cv-vit-b16-v3",
    }
