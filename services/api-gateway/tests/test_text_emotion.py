"""Unit tests for the text-emotion module (M3-05).

These use a fake classifier: they need no model download and run in CI in
milliseconds. The real-model latency check is in test_text_emotion_model.py
and only runs when RUN_MODEL_TESTS=1.
"""

import json
import logging
import threading
import time
from pathlib import Path

import pytest

from app import text_emotion
from app.text_emotion import (
    LABELS,
    TextEmotion,
    TextEmotionUnavailable,
    top2_from_scores,
)

SCHEMA = Path(__file__).parents[3] / "docs" / "contracts" / "context_object.schema.json"


def fake_scores(**overrides: float) -> dict[str, float]:
    """All 7 labels low, with the given ones raised."""
    scores = {label: 0.01 for label in LABELS}
    scores.update(overrides)
    return scores


def test_top2_is_the_two_highest_most_likely_first() -> None:
    top2 = top2_from_scores(fake_scores(sadness=0.71, fear=0.12, joy=0.05))
    assert top2 == [["sadness", 0.71], ["fear", 0.12]]


def test_scores_are_rounded_and_kept_between_0_and_1() -> None:
    top2 = top2_from_scores(fake_scores(joy=0.876543, neutral=1.0000001))
    assert top2 == [["neutral", 1.0], ["joy", 0.877]]


def test_ties_are_broken_by_label_name_so_results_are_stable() -> None:
    top2 = top2_from_scores({label: 1 / 7 for label in LABELS})
    assert [label for label, _ in top2] == ["anger", "disgust"]


def test_unknown_label_fails_loudly() -> None:
    # e.g. someone swaps in a 28-label GoEmotions model by mistake
    with pytest.raises(ValueError, match="annoyance"):
        top2_from_scores({"annoyance": 0.9, "joy": 0.1})


def test_analyse_returns_context_block_and_latency() -> None:
    module = TextEmotion(classifier=lambda text: fake_scores(sadness=0.6, anger=0.3))
    result = module.analyse("I had an awful day")

    assert result.as_context() == {"top2": [["sadness", 0.6], ["anger", 0.3]]}
    assert result.latency_ms >= 0
    assert result.model == "j-hartmann/emotion-english-distilroberta-base"


def test_text_block_matches_the_context_object_contract() -> None:
    """The `text` block must fit docs/contracts/context_object.schema.json."""
    schema = json.loads(SCHEMA.read_text())
    text_schema = schema["properties"]["text"]
    assert text_schema["required"] == ["top2"]

    block = TextEmotion(classifier=lambda text: fake_scores(joy=0.9)).analyse("yay").as_context()
    assert set(block) == {"top2"}
    assert 1 <= len(block["top2"]) <= 2
    for label, prob in block["top2"]:
        assert label in LABELS
        assert 0 <= prob <= 1


def test_blank_message_is_neutral_without_calling_the_model() -> None:
    def must_not_run(text: str) -> dict[str, float]:
        raise AssertionError("model should not be called for a blank message")

    result = TextEmotion(classifier=must_not_run).analyse("   ")
    assert result.top2 == [["neutral", 1.0]]


def test_long_message_is_cut_before_scoring() -> None:
    seen: list[str] = []

    def record(text: str) -> dict[str, float]:
        seen.append(text)
        return fake_scores(neutral=0.9)

    TextEmotion(max_chars=50, classifier=record).analyse("word " * 1000)
    assert len(seen[0]) == 50


def test_model_error_becomes_text_emotion_unavailable() -> None:
    def broken(text: str) -> dict[str, float]:
        raise RuntimeError("out of memory")

    with pytest.raises(TextEmotionUnavailable):
        TextEmotion(classifier=broken).analyse("hello")


def test_load_failure_becomes_text_emotion_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_model(*args: object) -> None:
        raise OSError("model not found")

    monkeypatch.setattr("app.text_emotion.load_hf_classifier", no_model)
    with pytest.raises(TextEmotionUnavailable, match="model not found"):
        TextEmotion().analyse("hello")


def test_model_is_loaded_once(monkeypatch: pytest.MonkeyPatch) -> None:
    loads: list[str] = []

    def fake_loader(model_name: str, revision: str, max_tokens: int):
        loads.append(model_name)
        return lambda text: fake_scores(joy=0.8)

    monkeypatch.setattr("app.text_emotion.load_hf_classifier", fake_loader)
    module = TextEmotion()
    module.warm_up()
    module.analyse("one")
    module.analyse("two")
    assert loads == ["j-hartmann/emotion-english-distilroberta-base"]


def test_message_text_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    secret = "my private message about my sister"
    module = TextEmotion(classifier=lambda text: fake_scores(sadness=0.9))
    # The "mirror" logger doesn't propagate to root; attach caplog's handler to it directly.
    mirror_logger = logging.getLogger("mirror")
    mirror_logger.setLevel("INFO")
    mirror_logger.addHandler(caplog.handler)
    try:
        module.analyse(secret)
    finally:
        mirror_logger.removeHandler(caplog.handler)
    assert any(r.getMessage() == "text_emotion" for r in caplog.records)  # the log was seen
    for record in caplog.records:
        assert secret not in record.getMessage()
        assert secret not in str(record.__dict__)


def test_model_revision_is_pinned_to_a_commit() -> None:
    # Reproducibility: a rebuild must load the same weights; the default is therefore a full
    # 40-character commit hash, never a moving branch like "main".
    import re

    from app.config import Settings

    default = Settings.model_fields["text_emotion_revision"].default
    assert re.fullmatch(r"[0-9a-f]{40}", default)
    assert TextEmotion().revision == default


@pytest.mark.parametrize(
    "bad_output",
    [{}, {"annoyance": 0.9, "joy": 0.1}, None, ["joy", 0.9]],
    ids=["no scores", "unknown label", "None", "not a dict"],
)
def test_malformed_model_output_becomes_text_emotion_unavailable(bad_output: object) -> None:
    # Owen (#50): bad output must take the text-only fallback, never crash the chat turn.
    module = TextEmotion(classifier=lambda text: bad_output)
    with pytest.raises(TextEmotionUnavailable):
        module.analyse("hello")


def test_simultaneous_first_calls_share_one_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    # Owen (#50): two requests at once must not build two instances (two model loads).
    built: list[object] = []

    class SlowTextEmotion:
        def __init__(self, **kwargs: object) -> None:
            time.sleep(0.05)  # widen the window in which a race would happen
            built.append(self)

    monkeypatch.setattr(text_emotion, "_instance", None)
    monkeypatch.setattr(text_emotion, "TextEmotion", SlowTextEmotion)

    start = threading.Barrier(8)
    results: list[object] = []

    def first_request() -> None:
        start.wait()
        results.append(text_emotion.get_text_emotion())

    threads = [threading.Thread(target=first_request) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(built) == 1
    assert all(result is built[0] for result in results)
