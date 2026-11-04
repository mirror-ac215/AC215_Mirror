import pytest


class TestRepository:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.flags: list[dict] = []

    async def add_message(
        self, session_id: str, role: str, text: str, safety_hit: bool
    ) -> str:
        message_id = f"test-{len(self.messages) + 1}"
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
        pass

    async def add_review_flag(self, patient_id: str, message_id: str) -> None:
        self.flags.append({"patient_id": patient_id, "message_id": message_id})


class TestLLM:
    async def stream(self, messages: list[dict[str, str]]):
        yield "test reply"


class TestCV:
    async def predict(self, image: bytes) -> dict:
        return {"face_found": False, "probs": {}}


@pytest.fixture(autouse=True)
def fake_gateway_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import chat
    from app.text_emotion import TextEmotion

    chat.repository = TestRepository()
    chat.llm_client = TestLLM()
    chat.cv_client = TestCV()
    chat.review_flags.clear()
    monkeypatch.setattr(
        chat,
        "get_text_emotion",
        lambda: TextEmotion(classifier=lambda _text: {"neutral": 1.0}),
    )
