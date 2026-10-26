"""Fusion (M3-06): one context object per turn, checked against the real contract."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.fusion import TurnHistory, fuse

SCHEMA = json.loads(
    (Path(__file__).parents[3] / "docs" / "contracts" / "context_object.schema.json").read_text(
        encoding="utf-8"
    )
)
VALIDATOR = Draft202012Validator(SCHEMA)


def face(label: str, prob: float, status: str = "ok") -> dict:
    return {"status": status, "top2": [[label, prob], ["neutral", 0.1]], "stability": 0.9,
            "window_s": 10.0, "n_frames": 8}


def words(label: str, prob: float) -> dict:
    return {"top2": [[label, prob], ["neutral", 0.1]]}


def turn(visual: dict, text: dict | None, history: TurnHistory | None = None) -> dict:
    context = fuse(visual, text, history or TurnHistory())
    VALIDATOR.validate(context)  # raises if the shape breaks the contract
    return context


def test_face_and_words_agree_across_label_names() -> None:
    context = turn(face("happy", 0.62), words("joy", 0.80))  # text says joy, camera says happy
    assert context["agreement"] == "agree"
    assert context["note"] == "main signal: face (happy, 0.62)"


def test_two_different_negative_emotions_still_agree() -> None:
    assert turn(face("angry", 0.5), words("sadness", 0.7))["agreement"] == "agree"


def test_disagreement_is_reported_so_the_prompt_asks() -> None:
    context = turn(face("happy", 0.6), words("sadness", 0.7))
    assert context["agreement"] == "disagree"
    assert context["tone_mode"] == "supportive"  # the words are negative


def test_face_never_leads_on_a_negative_emotion() -> None:
    # The gate is rarely right about sad faces (M3-04 sweep): the words lead instead.
    context = turn(face("sad", 0.55), words("neutral", 0.6))
    assert context["agreement"] == "disagree"
    assert context["note"] == "main signal: text (neutral, 0.60)"


@pytest.mark.parametrize("status", ["uncertain", "dropped", "camera_off"])
def test_a_face_the_gate_does_not_trust_is_ignored(status: str) -> None:
    visual = {"status": status} if status == "camera_off" else face("happy", 0.6, status)
    context = turn(visual, words("joy", 0.8))
    assert context["agreement"] == "n/a"
    assert context["note"] == "main signal: text (happy, 0.80)"


def test_weak_text_and_no_face_means_no_main_signal() -> None:
    context = turn({"status": "camera_off"}, words("sadness", 0.3))
    assert (context["agreement"], context["note"]) == ("n/a", "main signal: none")


def test_text_module_unavailable_still_gives_a_valid_context() -> None:
    context = turn(face("neutral", 0.6), None)
    assert context["text"] == {"top2": [["neutral", 0.0]]}
    assert context["note"] == "main signal: face (neutral, 0.60)"


def test_supportive_by_default_then_coach_after_two_steady_turns_of_three() -> None:
    history = TurnHistory()
    steady = (face("happy", 0.6), words("joy", 0.8))
    assert turn(*steady, history)["tone_mode"] == "supportive"  # one steady turn is not enough
    assert turn(*steady, history)["tone_mode"] == "coach"
    assert turn(face("happy", 0.6), words("sadness", 0.7), history)["tone_mode"] == "supportive"
    assert turn(*steady, history)["tone_mode"] == "coach"  # 2 of the last 3 were steady again


def test_turns_with_no_usable_signal_do_not_count_as_steady() -> None:
    history = TurnHistory()
    nothing = ({"status": "camera_off"}, None)
    for _ in range(3):
        assert turn(*nothing, history)["tone_mode"] == "supportive"
