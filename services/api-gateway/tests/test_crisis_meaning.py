"""M4-15 second safety layer: logic with a fake embedder (no model, runs in CI).

The real model is checked in tests/test_crisis_meaning_model.py (RUN_MODEL_TESTS=1).
"""

import logging
import math
import re

import pytest
from test_orchestration import FakeLLM, FakeRepository, text_emotion

from app.crisis_meaning import CrisisMeaning, CrisisMeaningUnavailable
from app.fusion import TurnHistory
from app.orchestration import ChatOrchestrator

CRISIS = (("vanish", "vanish forever never come back"),)
SAFE = (("holiday", "vanish to a beach holiday"),)


def bag_of_words(texts):
    """Unit vectors over the words seen so far: enough to test the decision rule."""
    vocab = sorted({w for t in CRISIS + SAFE for w in re.findall(r"[a-z]+", t[1].lower())})
    out = []
    for text in texts:
        words = re.findall(r"[a-z]+", text.lower())
        vec = [float(words.count(w)) for w in vocab]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        out.append([x / norm for x in vec])
    return out


def layer(threshold=0.5, margin=0.1, embedder=bag_of_words) -> CrisisMeaning:
    return CrisisMeaning(
        threshold=threshold,
        margin=margin,
        embedder=embedder,
        crisis_examples=CRISIS,
        safe_examples=SAFE,
    )


def test_fires_on_a_message_close_to_a_crisis_example() -> None:
    assert layer().check("I want to vanish forever and never come back") == "meaning-vanish"


def test_stays_quiet_when_the_message_is_closer_to_an_everyday_example() -> None:
    assert layer().check("I want to vanish to a beach holiday") is None


def test_stays_quiet_below_the_threshold() -> None:
    assert layer(threshold=0.99).check("vanish") is None


def test_margin_can_silence_a_message_close_to_both() -> None:
    message = "vanish forever never beach"
    score = layer().score(message)
    assert score.crisis > score.safe
    assert layer(threshold=0.0, margin=0.1).check(message) == "meaning-vanish"
    assert layer(threshold=0.0, margin=1.0).check(message) is None


def test_a_failed_load_is_unavailable_and_not_retried_every_message() -> None:
    calls = []

    def broken(texts):
        calls.append(texts)
        raise OSError("model not in cache")

    meaning = layer(embedder=broken)
    with pytest.raises(CrisisMeaningUnavailable):
        meaning.check("anything")
    with pytest.raises(CrisisMeaningUnavailable):
        meaning.check("anything else")
    assert len(calls) == 1


def turn_args(text: str) -> dict:
    return {
        "session_id": "session-1",
        "patient_id": "patient-1",
        "text": text,
        "visual": {"status": "camera_off"},
        "history": TurnHistory(),
        "conversation": [],
    }


@pytest.mark.anyio
async def test_a_meaning_hit_is_a_crisis_turn_with_a_review_flag_and_no_llm_call() -> None:
    repository, llm = FakeRepository(), FakeLLM()
    service = ChatOrchestrator(repository, llm, text_emotion(), layer())

    turn = await service.start_turn(**turn_args("I want to vanish forever and never come back"))

    assert turn.crisis is not None
    assert turn.safety_rule == "meaning-vanish"
    assert [token async for token in turn.tokens] == []
    assert len(repository.flags) == 1
    assert repository.messages[0]["safety_hit"] is True
    assert llm.calls == []


@pytest.mark.anyio
async def test_rules_crisis_does_not_call_the_meaning_layer() -> None:
    def must_not_run(texts):
        raise AssertionError("meaning layer called")

    service = ChatOrchestrator(
        FakeRepository(), FakeLLM(), text_emotion(), layer(embedder=must_not_run)
    )

    turn = await service.start_turn(**turn_args("I want to die"))

    assert turn.crisis is not None
    assert not turn.safety_rule.startswith("meaning-")


@pytest.mark.anyio
async def test_crisis_by_meaning_wins_over_a_medication_hit() -> None:
    service = ChatOrchestrator(FakeRepository(), FakeLLM(), text_emotion(), layer())

    turn = await service.start_turn(
        **turn_args("should I stop my meds? I want to vanish forever and never come back")
    )

    assert turn.crisis is not None
    assert turn.safety_rule == "meaning-vanish"


@pytest.mark.anyio
async def test_unavailable_meaning_layer_leaves_the_rules_in_charge() -> None:
    def broken(texts):
        raise OSError("no model")

    llm = FakeLLM()
    service = ChatOrchestrator(FakeRepository(), llm, text_emotion(), layer(embedder=broken))

    turn = await service.start_turn(**turn_args("I want to vanish forever and never come back"))

    assert turn.crisis is None
    assert [token async for token in turn.tokens]
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_message_text_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    secret = "I want to vanish forever and never come back"
    service = ChatOrchestrator(FakeRepository(), FakeLLM(), text_emotion(), layer())

    with caplog.at_level(logging.DEBUG, logger="mirror"):
        await service.start_turn(**turn_args(secret))

    assert secret not in caplog.text
