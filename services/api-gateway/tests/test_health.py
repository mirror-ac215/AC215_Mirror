import pytest
from httpx import ASGITransport, AsyncClient

import app.main


async def get_health() -> dict:
    async with AsyncClient(
        transport=ASGITransport(app=app.main.app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    return response.json()

"""monkeypatch is pytest's way of temporarily swapping in a fake.
The first two tests replace the real dependency check with "everything up" or "CV down",
so they test the gateway's logic without needing the other services to run.
The third test uses the real checks against port 1, where nothing ever runs, and
proves they correctly report "down" instead of crashing.
"""

@pytest.mark.anyio
async def test_health_ok_when_all_dependencies_are_up(monkeypatch) -> None:
    async def all_up(settings):
        return {"cv-service": "ok", "llm-service": "ok", "db": "ok"}

    monkeypatch.setattr(app.main, "check_dependencies", all_up)

    body = await get_health()

    assert body == {
        "status": "ok",
        "dependencies": {"cv-service": "ok", "llm-service": "ok", "db": "ok"}
    }

@pytest.mark.anyio
async def test_health_degraded_when_one_dependency_is_down(monkeypatch) -> None:
    async def cv_down(settings):
        return {"cv-service": "down", "llm-service": "ok", "db": "ok"}

    monkeypatch.setattr(app.main, "check_dependencies", cv_down)

    body = await get_health()

    assert body["status"] == "degraded"
    assert body["dependencies"]["cv-service"] == "down"

@pytest.mark.anyio
async def test_real_checks_report_down_when_nothing_is_running() -> None:
    from app.config import Settings
    from app.health import check_dependencies

    settings = Settings(
        cv_service_url="http://127.0.0.1:1",
        llm_service_url="http://127.0.0.1:1",
        db_host="127.0.01",
        db_port=1,
        dependency_timeout_s=0.5,
    )

    result = await check_dependencies(settings)

    assert result == {"cv-service": "down", "llm-service": "down", "db": "down"}
