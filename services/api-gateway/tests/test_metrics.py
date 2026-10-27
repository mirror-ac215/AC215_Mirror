"""Gateway metrics (M3-15): /metrics speaks Prometheus and counts what the gateway does."""

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
    metrics.record_gate({"status": "uncertain", "top2": [["sad", 0.4], ["neutral", 0.3]]})
    assert value("mirror_gateway_gate_total", status="uncertain") == before + 1

    labels = {"agreement": "disagree", "tone_mode": "supportive", "main_signal": "text"}
    before = value("mirror_gateway_fusion_total", **labels)
    metrics.record_fusion({"agreement": "disagree", "tone_mode": "supportive",
                           "note": "main signal: text (sad, 0.70); already checked in this session"})
    metrics.record_fusion({"agreement": "disagree", "tone_mode": "supportive", "note": "main signal: text (sad, 0.70)"})
    assert value("mirror_gateway_fusion_total", **labels) == before + 2
    metrics.record_fusion({"agreement": "n/a", "tone_mode": "supportive", "note": "main signal: none"})
    assert value("mirror_gateway_fusion_total", agreement="n/a", tone_mode="supportive", main_signal="none") >= 1
