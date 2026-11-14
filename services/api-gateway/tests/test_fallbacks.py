"""M4-04: every fallback path still ends a chat turn with a reply, a done event and saved rows.

Paths: camera off, cv-service down, low-confidence camera readings, and the language model
timing out or failing part-way through a reply. The real-container version of the CV and LLM
paths is infra/tests/test_compose_fallbacks.sh.
"""

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from conftest import auth_headers
from httpx import ASGITransport, AsyncClient

from app import chat, metrics
from app.chat import settings
from app.main import app
from app.orchestration import LLM_FALLBACK_REPLY, LLM_INTERRUPTED_NOTE

PATIENT = auth_headers(
    "00000000-0000-0000-0000-000000000201", "patient.alex@example.test", "patient"
)
FRAME = {"image": ("frame.jpg", b"fake-jpeg-bytes", "image/jpeg")}


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def fallbacks(reason: str) -> float:
    value = metrics.REGISTRY.get_sample_value("mirror_gateway_fallback_total", {"reason": reason})
    return value or 0.0


async def new_session(c: AsyncClient, consent: bool) -> str:
    response = await c.post("/sessions", json={"camera_consent": consent}, headers=PATIENT)
    assert response.status_code == 201
    return response.json()["session_id"]


async def chat_turn(c: AsyncClient, session_id: str, text: str = "Today was long") -> list:
    response = await c.post(
        f"/sessions/{session_id}/messages", json={"text": text}, headers=PATIENT
    )
    assert response.status_code == 200
    events = []
    for block in response.text.strip().split("\n\n"):
        event_line, data_line = block.split("\n")
        events.append(
            (event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: ")))
        )
    return events


def reply_text(events: list) -> str:
    return "".join(data["text"] for name, data in events if name == "token")


def saved_assistant_replies() -> list[str]:
    return [m["text"] for m in chat.repository.messages if m["role"] == "assistant"]


@pytest.mark.anyio
async def test_camera_off_turn_is_text_only() -> None:
    async with client() as c:
        session_id = await new_session(c, consent=False)
        events = await chat_turn(c, session_id)
    assert reply_text(events) == "test reply"
    name, done = events[-1]
    assert name == "done"
    assert done["context"]["visual"]["status"] == "camera_off"


@pytest.mark.anyio
async def test_cv_service_down_frame_gets_503_and_chat_still_works() -> None:
    class DownCV:
        async def predict(self, image: bytes) -> dict:
            raise httpx.ConnectError("cv-service is not running")

    chat.cv_client = DownCV()
    before = fallbacks("cv_unavailable")
    async with client() as c:
        session_id = await new_session(c, consent=True)
        frame = await c.post(f"/sessions/{session_id}/frames", files=FRAME, headers=PATIENT)
        events = await chat_turn(c, session_id)
    # The frontend turns a failed frame into "messages remain text-only".
    assert frame.status_code == 503
    assert fallbacks("cv_unavailable") == before + 1
    assert reply_text(events) == "test reply"
    name, done = events[-1]
    assert name == "done"
    # No reading reached the gate, so the face plays no part in this turn.
    assert done["context"]["visual"]["status"] == "dropped"
    assert "top2" not in done["context"]["visual"]


@pytest.mark.anyio
async def test_low_confidence_camera_readings_never_lead_the_turn() -> None:
    class FlatCV:
        """A face is found, but no emotion is clearly ahead: the gate must not trust it."""

        async def predict(self, image: bytes) -> dict:
            return {
                "face_found": True,
                "probs": {
                    "angry": 0.15,
                    "disgust": 0.14,
                    "fear": 0.14,
                    "happy": 0.15,
                    "neutral": 0.14,
                    "sad": 0.14,
                    "surprise": 0.14,
                },
            }

    chat.cv_client = FlatCV()
    async with client() as c:
        session_id = await new_session(c, consent=True)
        acks = [
            (await c.post(f"/sessions/{session_id}/frames", files=FRAME, headers=PATIENT)).json()
            for _ in range(settings.gate_min_frames)
        ]
        events = await chat_turn(c, session_id)
    assert acks[-1] == {"visual_status": "uncertain"}
    name, done = events[-1]
    assert name == "done"
    assert done["context"]["visual"]["status"] == "uncertain"
    assert reply_text(events) == "test reply"


@pytest.mark.anyio
async def test_llm_timeout_before_any_token_gives_the_gentle_reply_and_saves_it() -> None:
    class TimedOutLLM:
        async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
            raise httpx.ReadTimeout("llm-service took too long")
            yield ""  # pragma: no cover -- makes this an async generator

    chat.llm_client = TimedOutLLM()
    before = fallbacks("llm_unavailable")
    async with client() as c:
        session_id = await new_session(c, consent=False)
        events = await chat_turn(c, session_id)
    assert reply_text(events) == LLM_FALLBACK_REPLY
    assert "?" not in LLM_FALLBACK_REPLY and "988" not in LLM_FALLBACK_REPLY
    assert events[-1][0] == "done"
    assert saved_assistant_replies() == [LLM_FALLBACK_REPLY]
    assert fallbacks("llm_unavailable") == before + 1


@pytest.mark.anyio
async def test_llm_failing_part_way_finishes_the_sentence_gently() -> None:
    class BrokenLLM:
        async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
            yield "That sounds like a lot to carry. "
            raise httpx.RemoteProtocolError("stream closed")

    chat.llm_client = BrokenLLM()
    async with client() as c:
        session_id = await new_session(c, consent=False)
        events = await chat_turn(c, session_id)
    expected = "That sounds like a lot to carry. " + LLM_INTERRUPTED_NOTE
    assert reply_text(events) == expected
    assert events[-1][0] == "done"
    assert saved_assistant_replies() == [expected]


@pytest.mark.anyio
async def test_a_crisis_turn_never_waits_on_the_llm() -> None:
    class TimedOutLLM:
        async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
            raise AssertionError("a crisis turn must not call the language model")
            yield ""  # pragma: no cover

    chat.llm_client = TimedOutLLM()
    async with client() as c:
        session_id = await new_session(c, consent=False)
        events = await chat_turn(c, session_id, text="I want to die")
    assert [name for name, _ in events] == ["crisis"]
