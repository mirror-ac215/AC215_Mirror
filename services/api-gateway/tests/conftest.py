"""Safe test configuration and substitutes for gateway unit tests."""

import os
from collections.abc import Generator
from datetime import datetime

import bcrypt
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unit:unit@localhost:5432/unit")
os.environ.setdefault(
    "JWT_SIGNING_KEY", "unit-test-jwt-signing-key-with-adequate-length"
)

from app.auth import AuthenticatedUser, StoredUser, clear_login_attempts, get_user_lookup, issue_access_token
from app.chat import session_owners, sessions
from app.config import get_settings
from app.main import app
from app.schemas import Role


class TestRepository:
    def __init__(self) -> None:
        self.sessions: list[dict] = []
        self.messages: list[dict] = []
        self.flags: list[dict] = []

    async def add_session(
        self, session_id: str, patient_id: str, started_at: datetime, camera_consent: bool
    ) -> None:
        self.sessions.append({"id": session_id, "patient_id": patient_id})

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


class FakeUsers:
    """Deterministic seeded-user lookup that mirrors the Postgres users table."""

    def __init__(self) -> None:
        password_hash = bcrypt.hashpw(b"test-password", bcrypt.gensalt()).decode()
        self.users = {
            "clinician.ada@example.test": StoredUser(
                user_id="00000000-0000-0000-0000-000000000101",
                email="clinician.ada@example.test",
                role="clinician",
                password_hash=password_hash,
            ),
            "patient.alex@example.test": StoredUser(
                user_id="00000000-0000-0000-0000-000000000201",
                email="patient.alex@example.test",
                role="patient",
                password_hash=password_hash,
            ),
            "patient.bri@example.test": StoredUser(
                user_id="00000000-0000-0000-0000-000000000202",
                email="patient.bri@example.test",
                role="patient",
                password_hash=password_hash,
            ),
        }

    async def by_email(self, email: str) -> StoredUser | None:
        return self.users.get(email)


def auth_headers(user_id: str, email: str, role: Role) -> dict[str, str]:
    """Create a real signed test JWT; no fixed bearer tokens remain."""
    token = issue_access_token(
        AuthenticatedUser(user_id=user_id, email=email, role=role),
        signing_key=get_settings().jwt_signing_key,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def fake_gateway_dependencies(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    from app import chat
    from app.text_emotion import TextEmotion

    sessions.clear()
    session_owners.clear()
    clear_login_attempts()
    app.dependency_overrides[get_user_lookup] = lambda: FakeUsers()
    chat.repository = TestRepository()
    chat.llm_client = TestLLM()
    chat.cv_client = TestCV()
    chat.review_flags.clear()
    monkeypatch.setattr(
        chat,
        "get_text_emotion",
        lambda: TextEmotion(classifier=lambda _text: {"neutral": 1.0}),
    )
    yield
    app.dependency_overrides.clear()
    sessions.clear()
    session_owners.clear()
    clear_login_attempts()
