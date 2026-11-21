"""M4-17: the check-in cooldown starts only when the patient actually saw the check-in.

Each test runs a real ChatOrchestrator turn where face and words disagree. A fixed medication or
camera reply, an LLM fallback, or a check-in removed by the no-two-questions rule means the
patient never saw it, so the cooldown must not start.
"""

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

from app.fusion import TurnHistory
from app.orchestration import ChatOrchestrator
from app.text_emotion import TextEmotionResult

# Happy face, sad words: fusion says "disagree" and the prompt asks the model to check in.
HAPPY_FACE = {
    "status": "ok",
    "top2": [["happy", 0.7], ["neutral", 0.1]],
    "stability": 0.9,
    "window_s": 10.0,
    "n_frames": 8,
}
STATED = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "I am here."}]
ASKED = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "How are you?"}]
CHECK_IN = ["You look calm, but your words sound heavy. ", "How are you really feeling?"]


class FakeRepository:
    async def add_message(self, session_id: str, role: str, text: str, safety_hit: bool) -> str:
        return "message-id"

    async def add_emotion_window(self, session_id: str, context: dict) -> None:
        return None

    async def add_review_flag(self, patient_id: str, message_id: str) -> None:
        return None


class SadWords:
    def analyse(self, text: str) -> TextEmotionResult:
        return TextEmotionResult(
            top2=[["sadness", 0.8], ["neutral", 0.1]], latency_ms=1.0, model="fake"
        )


class FakeLLM:
    def __init__(self, tokens: list[str], fail_after: int | None = None) -> None:
        self.tokens, self.fail_after = tokens, fail_after

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        for index, token in enumerate(self.tokens):
            if index == self.fail_after:
                raise httpx.ReadTimeout("llm-service took too long")
            yield token
        if self.fail_after is not None and self.fail_after >= len(self.tokens):
            raise httpx.ReadTimeout("llm-service took too long")


async def run_turn(
    history: TurnHistory,
    llm: FakeLLM,
    text: str = "I'm fine I guess",
    conversation: list[dict[str, str]] = STATED,
) -> dict | None:
    turn = await ChatOrchestrator(FakeRepository(), llm, SadWords()).start_turn(
        session_id="session",
        patient_id="patient",
        text=text,
        visual=HAPPY_FACE,
        history=history,
        conversation=conversation,
    )
    [token async for token in turn.tokens]
    return turn.context


@pytest.mark.anyio
async def test_a_delivered_check_in_starts_the_cooldown() -> None:
    history = TurnHistory()
    context = await run_turn(history, FakeLLM(CHECK_IN))
    assert context["agreement"] == "disagree"
    assert history.last_check_in == 0


@pytest.mark.parametrize(
    "text", ["should I stop taking my meds", "can you see my camera"], ids=["medication", "camera"]
)
@pytest.mark.anyio
async def test_a_fixed_reply_does_not_start_the_cooldown(text: str) -> None:
    history = TurnHistory()
    context = await run_turn(history, FakeLLM(CHECK_IN), text=text)
    assert context["agreement"] == "disagree"
    assert history.last_check_in is None
    assert history.turns == 1  # the turn still counts towards any later cooldown


@pytest.mark.parametrize("fail_after", [0, 1], ids=["before-any-token", "part-way"])
@pytest.mark.anyio
async def test_an_llm_fallback_does_not_start_the_cooldown(fail_after: int) -> None:
    history = TurnHistory()
    await run_turn(history, FakeLLM(CHECK_IN, fail_after=fail_after))
    assert history.last_check_in is None


@pytest.mark.anyio
async def test_a_check_in_removed_by_the_no_two_questions_rule_does_not_start_the_cooldown() -> (
    None
):
    history = TurnHistory()
    await run_turn(history, FakeLLM(CHECK_IN), conversation=ASKED)
    assert history.last_check_in is None


@pytest.mark.anyio
async def test_a_reply_without_questions_after_a_question_still_counts() -> None:
    history = TurnHistory()
    await run_turn(
        history, FakeLLM(["You look calm, but your words sound heavy."]), conversation=ASKED
    )
    assert history.last_check_in == 0


@pytest.mark.anyio
async def test_mirror_checks_in_on_the_next_turn_when_the_last_one_never_reached_the_patient() -> (
    None
):
    history = TurnHistory()
    await run_turn(history, FakeLLM(CHECK_IN, fail_after=0))
    context = await run_turn(history, FakeLLM(CHECK_IN))
    assert context["agreement"] == "disagree"
    assert history.last_check_in == 1


@pytest.mark.anyio
async def test_a_crisis_turn_does_not_advance_the_turn_count() -> None:
    history = TurnHistory()
    await run_turn(history, FakeLLM(CHECK_IN), text="I want to die")
    assert history.turns == 0


async def open_turn(history: TurnHistory, llm: FakeLLM):
    """Start a turn but do not stream it yet, like a request whose reply is still in flight."""
    return await ChatOrchestrator(FakeRepository(), llm, SadWords()).start_turn(
        session_id="session",
        patient_id="patient",
        text="I'm fine I guess",
        visual=HAPPY_FACE,
        history=history,
        conversation=STATED,
    )


@pytest.mark.anyio
async def test_two_overlapping_turns_in_one_session_check_in_at_most_once() -> None:
    history = TurnHistory(checkin_cooldown=2)
    first = await open_turn(history, FakeLLM(CHECK_IN))
    second = await open_turn(history, FakeLLM(CHECK_IN))  # starts before the first is recorded
    assert first.context["agreement"] == "disagree"
    assert second.context["agreement"] == "n/a"
    assert second.context["note"].endswith("; check-in in progress in another reply")
    [token async for token in second.tokens]
    [token async for token in first.tokens]
    assert history.last_check_in == 1  # the first turn finished second, as turn index 1
    assert history.turns == 2
    assert not history.check_in_reserved


@pytest.mark.anyio
async def test_overlapping_turns_run_concurrently_still_check_in_once() -> None:
    history = TurnHistory()  # cooldown 5: any second check-in among 3 turns would be a bug

    class SlowLLM(FakeLLM):
        async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
            for token in self.tokens:
                await asyncio.sleep(0)  # let the other requests run between tokens
                yield token

    async def one_turn() -> dict | None:
        turn = await open_turn(history, SlowLLM(CHECK_IN))
        [token async for token in turn.tokens]
        return turn.context

    contexts = await asyncio.gather(*(one_turn() for _ in range(3)))
    assert [c["agreement"] for c in contexts].count("disagree") == 1
    assert history.turns == 3


@pytest.mark.anyio
async def test_an_abandoned_reply_frees_the_check_in_for_a_later_turn() -> None:
    history = TurnHistory()
    turn = await open_turn(history, FakeLLM(CHECK_IN))
    stream = turn.tokens
    await stream.__anext__()  # the patient's browser receives the first words, then leaves
    await stream.aclose()
    assert history.last_check_in is None
    assert not history.check_in_reserved
    context = await run_turn(history, FakeLLM(CHECK_IN))
    assert context["agreement"] == "disagree"
