"""M3-10 gateway turn integration with fake CV/LLM and persistence."""

from collections.abc import AsyncIterator

import pytest

from app.fusion import TurnHistory
from app.gating import FrameReading
from app.orchestration import ChatOrchestrator
from app.text_emotion import TextEmotion


class FakeRepository:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.windows: list[dict] = []
        self.flags: list[dict] = []

    async def add_message(
        self, session_id: str, role: str, text: str, safety_hit: bool
    ) -> str:
        message_id = f"message-{len(self.messages) + 1}"
        self.messages.append(
            {
                "id": message_id,
                "session_id": session_id,
                "role": role,
                "text": text,
                "safety_hit": safety_hit,
            }
        )
        return message_id

    async def add_emotion_window(self, session_id: str, context: dict) -> None:
        self.windows.append({"session_id": session_id, "context": context})

    async def add_review_flag(self, patient_id: str, message_id: str) -> None:
        self.flags.append({"patient_id": patient_id, "message_id": message_id})


class FakeLLM:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        self.calls.append(messages)
        yield "I hear you. "
        yield "What would help today?"


def text_emotion() -> TextEmotion:
    return TextEmotion(classifier=lambda _text: {"sadness": 0.8, "neutral": 0.15})


@pytest.mark.anyio
async def test_normal_turn_runs_emotion_fusion_llm_and_persists_both_messages_and_window() -> (
    None
):
    repository = FakeRepository()
    llm = FakeLLM()
    service = ChatOrchestrator(
        repository=repository, llm=llm, text_emotion=text_emotion()
    )
    visual = {"status": "camera_off"}

    turn = await service.start_turn(
        session_id="session-1",
        patient_id="patient-1",
        text="Today was hard",
        visual=visual,
        history=TurnHistory(),
        conversation=[],
    )
    tokens = [token async for token in turn.tokens]

    assert tokens == ["I hear you. ", "What would help today?"]
    assert [message["role"] for message in repository.messages] == [
        "patient",
        "assistant",
    ]
    assert repository.messages[0]["text"] == "Today was hard"
    assert repository.messages[0]["safety_hit"] is False
    assert repository.messages[1]["text"] == "I hear you. What would help today?"
    assert repository.windows[0]["context"]["text"]["top2"][0] == ["sadness", 0.8]
    assert repository.windows[0]["context"]["visual"] == visual
    assert repository.flags == []
    assert llm.calls[0][-1] == {"role": "user", "content": "Today was hard"}
    assert turn.context["tone_mode"] == "supportive"


@pytest.mark.anyio
async def test_crisis_persists_patient_message_and_review_flag_without_calling_llm() -> (
    None
):
    repository = FakeRepository()
    llm = FakeLLM()
    service = ChatOrchestrator(
        repository=repository, llm=llm, text_emotion=text_emotion()
    )

    turn = await service.start_turn(
        session_id="session-2",
        patient_id="patient-2",
        text="I want to die",
        visual={"status": "camera_off"},
        history=TurnHistory(),
        conversation=[],
    )

    assert turn.crisis is not None
    assert repository.messages == [
        {
            "id": "message-1",
            "session_id": "session-2",
            "role": "patient",
            "text": "I want to die",
            "safety_hit": True,
        }
    ]
    assert repository.flags == [{"patient_id": "patient-2", "message_id": "message-1"}]
    assert repository.windows == []
    assert llm.calls == []


@pytest.mark.anyio
async def test_http_turn_forwards_fake_llm_sse_and_uses_fake_cv_and_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from httpx import ASGITransport, AsyncClient

    from app import chat
    from app.main import app

    repository = FakeRepository()
    llm = FakeLLM()

    class FakeCV:
        async def predict(self, image: bytes) -> dict:
            assert image == b"jpeg"
            return {"face_found": False, "probs": {}}

    monkeypatch.setattr(chat, "repository", repository)
    monkeypatch.setattr(chat, "llm_client", llm)
    monkeypatch.setattr(chat, "cv_client", FakeCV())
    monkeypatch.setattr(chat, "get_text_emotion", text_emotion)
    headers = {"Authorization": "Bearer dev-patient-token"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/sessions", json={"camera_consent": True}, headers=headers
        )
        session_id = created.json()["session_id"]
        frame = await client.post(
            f"/sessions/{session_id}/frames",
            files={"image": ("frame.jpg", b"jpeg", "image/jpeg")},
            headers=headers,
        )
        response = await client.post(
            f"/sessions/{session_id}/messages",
            json={"text": "Today was hard"},
            headers=headers,
        )

    assert frame.status_code == 202
    assert response.status_code == 200
    assert "event: token" in response.text
    assert "What would help today?" in response.text
    assert [message["role"] for message in repository.messages] == [
        "patient",
        "assistant",
    ]
    assert len(repository.windows) == 1
    assert llm.calls


def test_cv_reading_is_converted_to_a_gate_input_without_storing_image_bytes() -> None:
    reading = FrameReading.from_cv_payload(
        {
            "face_found": True,
            "probs": {
                "angry": 0.01,
                "disgust": 0.01,
                "fear": 0.01,
                "happy": 0.01,
                "neutral": 0.01,
                "sad": 0.94,
                "surprise": 0.01,
            },
        },
        timestamp=42.0,
    )

    assert reading.ts == 42.0
    assert reading.face_found is True
    assert reading.probs["sad"] == 0.94
