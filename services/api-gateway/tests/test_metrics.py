"""Gateway metrics (M3-15): /metrics speaks Prometheus and counts what the gateway does."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app import metrics
from app.main import app
from app.text_emotion import TextEmotion, TextEmotionUnavailable

PATIENT = {"Authorization": "Bearer dev-patient-token"}


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def value(name: str, **labels: str) -> float:
    """Current value of one metric series (0 if it was never touched)."""
    return metrics.REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.mark.anyio
async def test_metrics_endpoint_speaks_prometheus() -> None:
    async with client() as c:
        response = await c.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "mirror_gateway_requests_total" in response.text
    assert "mirror_gateway_request_seconds" in response.text


@pytest.mark.anyio
async def test_requests_are_counted_by_route_pattern_not_by_real_path() -> None:
    labels = {"route": "/sessions/{session_id}/frames", "method": "POST", "status": "401"}
    before = value("mirror_gateway_requests_total", **labels)
    async with client() as c:
        await c.post("/sessions/some-real-session-id/frames")  # no token -> 401
    assert value("mirror_gateway_requests_total", **labels) == before + 1
    # The session id never becomes a label.
    async with client() as c:
        assert "some-real-session-id" not in (await c.get("/metrics")).text


@pytest.mark.anyio
async def test_request_latency_is_recorded() -> None:
    before = value("mirror_gateway_request_seconds_count", route="/metrics")
    async with client() as c:
        await c.get("/metrics")
    assert value("mirror_gateway_request_seconds_count", route="/metrics") == before + 1


@pytest.mark.anyio
async def test_a_crisis_hit_is_counted_by_rule_never_by_text() -> None:
    async with client() as c:
        session = (await c.post("/sessions", json={"camera_consent": False}, headers=PATIENT)).json()
        await c.post(f"/sessions/{session['session_id']}/messages", json={"text": "I want to kill myself"},
                     headers=PATIENT)
        body = (await c.get("/metrics")).text
    assert value("mirror_gateway_crisis_hits_total", rule="kill-self") >= 1
    assert "kill myself" not in body


def test_text_emotion_time_and_fallbacks_are_counted() -> None:
    scored = value("mirror_gateway_text_emotion_seconds_count")
    TextEmotion(classifier=lambda text: {"joy": 0.9, "neutral": 0.1}).analyse("yay")
    assert value("mirror_gateway_text_emotion_seconds_count") == scored + 1

    unavailable = value("mirror_gateway_text_emotion_unavailable_total")

    def broken(text: str) -> dict[str, float]:
        raise RuntimeError("model crashed")

    with pytest.raises(TextEmotionUnavailable):
        TextEmotion(classifier=broken).analyse("hello")
    assert value("mirror_gateway_text_emotion_unavailable_total") == unavailable + 1


def test_gate_and_fusion_outcomes_are_counted() -> None:
    # The chat endpoint (M3-10) calls these once per turn, where it calls gate() and fuse().
    before = value("mirror_gateway_gate_total", status="uncertain")
    metrics.record_gate("uncertain")
    assert value("mirror_gateway_gate_total", status="uncertain") == before + 1

    labels = {"agreement": "disagree", "tone_mode": "supportive", "main_signal": "text"}
    before = value("mirror_gateway_fusion_total", **labels)
    metrics.record_fusion("disagree", "supportive", "text")
    assert value("mirror_gateway_fusion_total", **labels) == before + 1


# Owen (#63): labels come from fixed lists, never from free text.
@pytest.mark.parametrize(
    "bad",
    ["main signal: face (sad, 0.70)", "FACE", "", None, "sad"],
    ids=["note text", "wrong case", "empty", "None", "an emotion"],
)
def test_unknown_label_values_are_counted_as_invalid(bad) -> None:
    gate_before = value("mirror_gateway_gate_total", status="invalid")
    metrics.record_gate(bad)
    assert value("mirror_gateway_gate_total", status="invalid") == gate_before + 1

    labels = {"agreement": "invalid", "tone_mode": "invalid", "main_signal": "invalid"}
    before = value("mirror_gateway_fusion_total", **labels)
    metrics.record_fusion(bad, bad, bad)
    assert value("mirror_gateway_fusion_total", **labels) == before + 1


# Owen (#63): /metrics must not be reachable from the browser through Caddy.
def test_caddy_blocks_public_metrics() -> None:
    caddyfile = (Path(__file__).parents[3] / "infra" / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    block = caddyfile.index("handle /api/metrics* {")
    assert "respond 404" in caddyfile[block : caddyfile.index("}", block)]
    assert block < caddyfile.index("handle_path /api/*")  # listed before the general /api proxy
