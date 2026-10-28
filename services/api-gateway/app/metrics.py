"""Prometheus metrics for the api-gateway (M3-15), served at GET /metrics.

What is counted:
- every HTTP request: route pattern, method, status code, and how long it took;
- crisis-check hits per rule (the rule id only, never the message text);
- the text-emotion module: scoring time, and how often it was unavailable (text-only fallback);
- the gate and fusion outcomes, through record_gate() and record_fusion(). The chat endpoint
  (M3-10) calls them once per turn, where it calls gate() and fuse(). Until then they stay at 0.

Routes are recorded by their pattern (/sessions/{session_id}/messages), never the real path,
so the number of series stays small and no session id ends up in the metrics.
Gate and fusion labels come from fixed lists only; anything else is counted as "invalid".

/metrics is not public: Caddy answers /api/metrics with 404 (infra/caddy/Caddyfile).
"""

from __future__ import annotations

from fastapi import Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

# Our own registry: /metrics shows only Mirror's metrics, and tests can read exact values.
REGISTRY = CollectorRegistry()

REQUESTS = Counter(
    "mirror_gateway_requests_total", "HTTP requests by route pattern, method and status code",
    ["route", "method", "status"], registry=REGISTRY,
)
REQUEST_SECONDS = Histogram(
    "mirror_gateway_request_seconds", "Time to answer an HTTP request (streams: until the first byte)",
    ["route"], registry=REGISTRY,
)
CRISIS_HITS = Counter(
    "mirror_gateway_crisis_hits_total", "Crisis-check hits by rule id (M3-07)", ["rule"], registry=REGISTRY,
)
TEXT_EMOTION_SECONDS = Histogram(
    "mirror_gateway_text_emotion_seconds", "Time to score one message (M3-05)", registry=REGISTRY,
)
TEXT_EMOTION_UNAVAILABLE = Counter(
    "mirror_gateway_text_emotion_unavailable_total",
    "Messages that went on without a text-emotion reading (fallback)", registry=REGISTRY,
)
GATE = Counter(
    "mirror_gateway_gate_total", "Gate outcome per turn: ok / uncertain / dropped / camera_off (M3-04)",
    ["status"], registry=REGISTRY,
)
FUSION = Counter(
    "mirror_gateway_fusion_total", "Fusion outcome per turn (M3-06)",
    ["agreement", "tone_mode", "main_signal"], registry=REGISTRY,
)


# The only values a gate or fusion label can take (docs/contracts/context_object.schema.json).
GATE_STATUSES = ("ok", "uncertain", "dropped", "camera_off")
AGREEMENTS = ("agree", "disagree", "n/a")
TONE_MODES = ("coach", "supportive")
MAIN_SIGNALS = ("face", "text", "none")


def _closed(value: object, allowed: tuple[str, ...]) -> str:
    """The value if it is on the list, else "invalid": a label never takes free text."""
    return value if value in allowed else "invalid"


def route_of(request: Request) -> str:
    """The matched route pattern, e.g. /sessions/{session_id}/frames; 'unmatched' for a 404 path."""
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


def record_gate(status: str) -> None:
    """Count one gate result (the `status` of the context object's `visual` block)."""
    GATE.labels(status=_closed(status, GATE_STATUSES)).inc()


def record_fusion(agreement: str, tone_mode: str, main_signal: str) -> None:
    """Count one fused turn. main_signal is face / text / none, passed in by the caller (M3-10)."""
    FUSION.labels(
        agreement=_closed(agreement, AGREEMENTS),
        tone_mode=_closed(tone_mode, TONE_MODES),
        main_signal=_closed(main_signal, MAIN_SIGNALS),
    ).inc()


def render() -> tuple[bytes, str]:
    """The /metrics body and its content type (Prometheus text format)."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
