"""M4-16: break suggestion after ~2 h and a non-urgent clinician flag after ~3 h."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import auth_headers
from test_orchestration import FakeLLM, FakeRepository, text_emotion

from app.fusion import TurnHistory
from app.orchestration import ChatOrchestrator
from app.wellbeing import BREAK_MESSAGE, SessionClock

START = datetime(2026, 11, 27, 9, 0, tzinfo=UTC)
CAMERA_OFF = {"status": "camera_off"}


class FlagRepository(FakeRepository):
    """Records the flag reason as well (crisis flags keep the old two-argument call)."""

    async def add_review_flag(self, patient_id: str, message_id: str, reason="crisis") -> None:
        self.flags.append({"patient_id": patient_id, "message_id": message_id, "reason": reason})


def clock_at(minutes: float) -> SessionClock:
    return SessionClock(
        started_at=START,
        break_after_min=120,
        flag_after_min=180,
        now=lambda: START + timedelta(minutes=minutes),
    )


async def turn(repository, clock, text="It's been a long day"):
    orchestrator = ChatOrchestrator(repository, FakeLLM(), text_emotion())
    result = await orchestrator.start_turn(
        session_id="session-1",
        patient_id="patient-1",
        text=text,
        visual=CAMERA_OFF,
        history=TurnHistory(),
        conversation=[],
        clock=clock,
    )
    [token async for token in result.tokens]
    return result


@pytest.mark.parametrize(
    ("minutes", "break_due", "flag_due"),
    [(119, False, False), (120, True, False), (179, True, False), (180, True, True)],
)
def test_thresholds(minutes: float, break_due: bool, flag_due: bool) -> None:
    clock = clock_at(minutes)
    assert clock.break_due() is break_due
    assert clock.flag_due() is flag_due


def test_each_action_happens_once() -> None:
    clock = clock_at(200)
    clock.break_suggested = True
    clock.flagged = True
    assert not clock.break_due()
    assert not clock.flag_due()


@pytest.mark.anyio
async def test_short_session_gets_no_suggestion_and_no_flag() -> None:
    repository = FlagRepository()
    result = await turn(repository, clock_at(30))
    assert result.wellbeing is None
    assert repository.flags == []


@pytest.mark.anyio
async def test_two_hours_suggests_a_break_without_flagging() -> None:
    repository = FlagRepository()
    result = await turn(repository, clock_at(125))
    assert result.wellbeing == {"kind": "break_suggestion", "message": BREAK_MESSAGE}
    assert repository.flags == []


@pytest.mark.anyio
async def test_three_hours_flags_once_as_long_session() -> None:
    repository = FlagRepository()
    clock = clock_at(185)
    first = await turn(repository, clock)
    await turn(repository, clock)

    assert repository.flags == [
        {"patient_id": "patient-1", "message_id": first.message_id, "reason": "long_session"}
    ]
    # The reply itself is unchanged: the flag is quiet, not a crisis.
    assert first.crisis is None


@pytest.mark.anyio
async def test_crisis_in_a_long_session_keeps_only_the_crisis_flag() -> None:
    repository = FlagRepository()
    result = await turn(repository, clock_at(200), text="I want to kill myself")
    assert result.crisis is not None
    assert result.wellbeing is None
    assert [flag["reason"] for flag in repository.flags] == ["crisis"]


@pytest.mark.anyio
async def test_a_failed_flag_does_not_block_the_reply_and_is_retried() -> None:
    class BrokenOnce(FlagRepository):
        failed = False

        async def add_review_flag(self, patient_id, message_id, reason="crisis") -> None:
            if not self.failed:
                self.failed = True
                raise ConnectionError("db down")
            await super().add_review_flag(patient_id, message_id, reason)

    repository = BrokenOnce()
    clock = clock_at(185)
    first = await turn(repository, clock)
    assert first.message_id
    assert repository.flags == []
    await turn(repository, clock)
    assert [flag["reason"] for flag in repository.flags] == ["long_session"]


@pytest.mark.anyio
async def test_stream_sends_the_break_after_the_reply_and_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from httpx import ASGITransport, AsyncClient

    from app import chat
    from app.main import app

    monkeypatch.setattr(chat, "repository", FlagRepository())
    monkeypatch.setattr(chat, "llm_client", FakeLLM())
    monkeypatch.setattr(chat, "get_text_emotion", text_emotion)
    headers = auth_headers(
        "00000000-0000-0000-0000-000000000201", "patient.alex@example.test", "patient"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/sessions", json={"camera_consent": False}, headers=headers)
        session_id = created.json()["session_id"]
        chat.session_clocks[session_id].now = lambda: START + timedelta(hours=2)
        chat.session_clocks[session_id].started_at = START
        first = await client.post(
            f"/sessions/{session_id}/messages", json={"text": "Still here"}, headers=headers
        )
        second = await client.post(
            f"/sessions/{session_id}/messages", json={"text": "Still here"}, headers=headers
        )

    events = [line for line in first.text.splitlines() if line.startswith("event:")]
    assert events[-2:] == ["event: wellbeing", "event: done"]
    assert "break_suggestion" in first.text
    assert "event: wellbeing" not in second.text
