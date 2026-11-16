"""M4-15 second safety layer: logic with a fake embedder (no model, runs in CI).

The real model is checked in tests/test_crisis_meaning_model.py (RUN_MODEL_TESTS=1).
"""

import logging
import math
import re

import pytest
from test_orchestration import FakeLLM, FakeRepository, text_emotion

import app.main as gateway_main
from app import metrics
from app.crisis_meaning import SAFE_EXAMPLES, CrisisMeaning, CrisisMeaningUnavailable
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


def test_real_model_false_alarm_regressions_are_active_safe_examples() -> None:
    """CI-identified everyday false alarms must be represented in the active safe controls."""
    safe_texts = {text for _, text in SAFE_EXAMPLES}
    assert {
        "the train was so late I wanted to scream",
        "I gave my cat to my sister while I travel.",
        "I'm going to end it with him tonight",
        "I want to end it on a good note",
    } <= safe_texts


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


@pytest.mark.anyio
async def test_enabled_meaning_layer_refuses_startup_when_it_cannot_warm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured safety layer cannot silently degrade to known-miss behavior."""
    monkeypatch.setattr(
        gateway_main,
        "get_crisis_meaning",
        lambda: layer(embedder=lambda _: (_ for _ in ()).throw(OSError("missing"))),
    )

    with pytest.raises(CrisisMeaningUnavailable):
        async with gateway_main.lifespan(gateway_main.app):
            pass


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


def meaning_fallbacks() -> float:
    value = metrics.REGISTRY.get_sample_value(
        "mirror_gateway_fallback_total", {"reason": "crisis_meaning_unavailable"}
    )
    return value or 0.0


@pytest.mark.anyio
async def test_a_failed_load_is_counted_and_logged_and_rules_still_catch_crisis(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(texts):
        raise OSError("no model")

    service = ChatOrchestrator(FakeRepository(), FakeLLM(), text_emotion(), layer(embedder=broken))
    before = meaning_fallbacks()

    with caplog.at_level(logging.WARNING, logger="mirror"):
        everyday = await service.start_turn(**turn_args("I had a quiet day at work"))
        rules_crisis = await service.start_turn(**turn_args("I want to die"))

    # The everyday message was checked by the rules alone: counted once.
    assert everyday.crisis is None
    assert meaning_fallbacks() == before + 1
    # The deterministic rules stay active (and do not need the meaning layer).
    assert rules_crisis.crisis is not None
    assert not rules_crisis.safety_rule.startswith("meaning-")
    fallbacks = [r for r in caplog.records if r.getMessage() == "crisis_meaning_fallback"]
    assert [r.stage for r in fallbacks] == ["load"]
    assert "quiet day" not in caplog.text


@pytest.mark.anyio
async def test_a_failed_inference_is_counted_with_its_stage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fails_on_messages(texts):
        if texts == [t for _, t in CRISIS] or texts == [t for _, t in SAFE]:
            return bag_of_words(texts)  # the examples load fine
        raise RuntimeError("inference failed")

    service = ChatOrchestrator(
        FakeRepository(), FakeLLM(), text_emotion(), layer(embedder=fails_on_messages)
    )
    before = meaning_fallbacks()

    with caplog.at_level(logging.WARNING, logger="mirror"):
        turn = await service.start_turn(**turn_args("I had a quiet day at work"))

    assert turn.crisis is None
    assert meaning_fallbacks() == before + 1
    fallbacks = [r for r in caplog.records if r.getMessage() == "crisis_meaning_fallback"]
    assert [r.stage for r in fallbacks] == ["inference"]


@pytest.mark.anyio
async def test_message_text_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    secret = "I want to vanish forever and never come back"
    service = ChatOrchestrator(FakeRepository(), FakeLLM(), text_emotion(), layer())

    with caplog.at_level(logging.DEBUG, logger="mirror"):
        await service.start_turn(**turn_args(secret))

    assert secret not in caplog.text
