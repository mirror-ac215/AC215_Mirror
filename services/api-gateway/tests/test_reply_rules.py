"""No two questions in a row, and the fixed camera reply."""

from collections.abc import AsyncIterator

import pytest
from app import safety
from app.fusion import TurnHistory
from app.orchestration import QUESTION_FALLBACK, ChatOrchestrator, drop_questions
from app.text_emotion import TextEmotionUnavailable


class FakeRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[str, str]] = []

    async def add_message(self, session_id: str, role: str, text: str, safety_hit: bool) -> str:
        self.saved.append((role, text))
        return "message-id"

    async def add_emotion_window(self, session_id: str, context: dict) -> None:
        return None

    async def add_review_flag(self, patient_id: str, message_id: str) -> None:
        return None


class FakeLLM:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.calls = 0

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        self.calls += 1
        for token in self.tokens:
            yield token


class NoTextEmotion:
    def analyse(self, text: str) -> None:
        raise TextEmotionUnavailable("not used here")


async def run_turn(
    text: str, tokens: list[str], conversation: list[dict[str, str]]
) -> tuple[list[str], FakeRepository, FakeLLM]:
    repository, llm = FakeRepository(), FakeLLM(tokens)
    turn = await ChatOrchestrator(repository, llm, NoTextEmotion()).start_turn(
        session_id="session",
        patient_id="patient",
        text=text,
        visual={"status": "camera_off"},
        history=TurnHistory(),
        conversation=conversation,
    )
    return [token async for token in turn.tokens], repository, llm


ASKED = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "How are you?"}]
STATED = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "I am here."}]


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("That is a lot. How do you feel?", "That is a lot."),
        ("How do you feel? That is a lot.", "That is a lot."),
        ("That is a lot.", "That is a lot."),
        ("How do you feel?", QUESTION_FALLBACK),  # nothing else would be left
        ("How do you feel? What happened?", QUESTION_FALLBACK),
        ("That is a lot.How do you feel?", "That is a lot."),
        ('She said "why me?" That hurts.', "That hurts."),
        ("Really?! That is hard.", "That is hard."),
        ('That is hard. "Why me?"', "That is hard."),
    ],
)
def test_drop_questions(reply: str, expected: str) -> None:
    assert drop_questions(reply) == expected


@pytest.mark.anyio
async def test_question_after_a_question_is_removed_and_saved_without_it() -> None:
    tokens, repository, _ = await run_turn("tired", ["That is a lot. ", "How do you feel?"], ASKED)
    assert tokens == ["That is a lot."]
    assert ("assistant", "That is a lot.") in repository.saved


@pytest.mark.anyio
async def test_question_only_reply_after_a_question_becomes_the_fixed_line() -> None:
    tokens, repository, _ = await run_turn("tired", ["How ", "do you feel?"], ASKED)
    assert tokens == [QUESTION_FALLBACK]
    assert ("assistant", QUESTION_FALLBACK) in repository.saved


@pytest.mark.anyio
async def test_reply_after_a_statement_keeps_streaming_with_its_question() -> None:
    tokens, repository, _ = await run_turn("tired", ["That is a lot. ", "How do you feel?"], STATED)
    assert tokens == ["That is a lot. ", "How do you feel?"]
    assert ("assistant", "That is a lot. How do you feel?") in repository.saved


@pytest.mark.parametrize(
    "text",
    [
        "can you see my camera",
        "Are you recording me?",
        "Do you keep my video?",
        "What does the camera think I'm feeling?",
    ],
)
@pytest.mark.anyio
async def test_camera_question_gets_the_fixed_reply_not_the_llm(text: str) -> None:
    tokens, _, llm = await run_turn(text, ["not used"], ASKED)
    assert tokens == [safety.CAMERA_REPLY]
    assert llm.calls == 0


def test_crisis_and_medication_win_over_a_camera_question() -> None:
    assert safety.check("can you see me? I want to die").kind == "crisis"
    assert safety.check("can you see me? should I stop taking my meds").kind == "medication"


@pytest.mark.parametrize(
    "text",
    [
        "I can see my sister tomorrow",
        "my camera broke at work",
        "I downloaded an app that helps me know how I feel",
        "my therapist said the app can tell when my mood dips",
        "Are you saving my messages?",
        "are you saving this conversation",
        "are you recording our chat",
        "are you watching the game tonight",
        "do you see me as a failure?",
        "can you see me struggling",
        "could you look at me differently",
    ],
)
def test_ordinary_messages_are_not_camera_questions(text: str) -> None:
    assert safety.check(text).kind is None
