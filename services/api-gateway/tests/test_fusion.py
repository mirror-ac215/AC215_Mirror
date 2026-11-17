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
    return {
        "status": status,
        "top2": [[label, prob], ["neutral", 0.1]],
        "stability": 0.9,
        "window_s": 10.0,
        "n_frames": 8,
    }


def words(label: str, prob: float) -> dict:
    return {"top2": [[label, prob], ["neutral", 0.1]]}


def turn(visual: dict, text: dict | None, history: TurnHistory | None = None) -> dict:
    """One finished chat turn: fuse, check the contract, then record it (as the gateway will)."""
    history = history if history is not None else TurnHistory()
    context = fuse(visual, text, history)
    VALIDATOR.validate(context)  # raises if the shape breaks the contract
    history.record(context, reply_delivered=True)
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


def test_negative_face_with_calm_words_is_a_disagree_on_purpose() -> None:
    # The gate is rarely right about sad faces (M3-04 sweep), so the words lead. But the face still
    # counts for agreement: Mirror checks in gently. That is the safe direction; keep it (#60 review).
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


def test_negative_words_lead_over_a_calm_face() -> None:
    # Julie (#60), D-004: what the patient tells us outweighs what the camera sees.
    context = turn(face("neutral", 0.6), words("sadness", 0.7))
    assert context["agreement"] == "disagree"
    assert context["note"] == "main signal: text (sad, 0.70)"
    assert context["tone_mode"] == "supportive"


def test_after_a_check_in_mirror_takes_their_word_until_the_cooldown_passes() -> None:
    # D-004: check in on a disagreement, then take the patient's word for a while.
    history = TurnHistory()
    mixed = (face("happy", 0.6), words("sadness", 0.7))
    assert turn(*mixed, history)["agreement"] == "disagree"
    later = turn(*mixed, history)
    assert later["agreement"] == "n/a"
    assert later["note"] == "main signal: text (sad, 0.70); checked in recently"
    # Agreement is still reported normally after the check-in.
    assert turn(face("happy", 0.6), words("joy", 0.8), history)["agreement"] == "agree"


def test_mirror_may_check_in_again_once_the_cooldown_has_passed() -> None:
    # M4-17 (D-004 update): the answer counts for that moment, not the whole session.
    history = TurnHistory(checkin_cooldown=3)
    mixed = (face("happy", 0.6), words("sadness", 0.7))
    agreements = [turn(*mixed, history)["agreement"] for _ in range(7)]
    # Turn 0 checks in, turns 1-2 wait, turn 3 may ask again, then 4-5 wait, turn 6 again.
    assert agreements == ["disagree", "n/a", "n/a", "disagree", "n/a", "n/a", "disagree"]


def test_the_cooldown_counts_every_turn_not_only_disagreements() -> None:
    history = TurnHistory(checkin_cooldown=3)
    mixed = (face("happy", 0.6), words("sadness", 0.7))
    steady = (face("happy", 0.6), words("joy", 0.8))
    assert turn(*mixed, history)["agreement"] == "disagree"
    assert turn(*steady, history)["agreement"] == "agree"
    assert turn(*steady, history)["agreement"] == "agree"
    assert turn(*mixed, history)["agreement"] == "disagree"


def test_mirror_never_checks_in_on_back_to_back_turns() -> None:
    history = TurnHistory(checkin_cooldown=2)  # the shortest allowed cooldown
    mixed = (face("happy", 0.6), words("sadness", 0.7))
    agreements = [turn(*mixed, history)["agreement"] for _ in range(5)]
    assert agreements == ["disagree", "n/a", "disagree", "n/a", "disagree"]
    with pytest.raises(ValueError):
        TurnHistory(checkin_cooldown=1)


def test_fuse_does_not_change_the_history_so_a_retry_is_safe() -> None:
    # Julie (#60): if M3-10 re-fuses the same turn (e.g. after an LLM timeout), nothing is counted twice.
    history = TurnHistory()
    steady = (face("happy", 0.6), words("joy", 0.8))
    turn(*steady, history)
    first = fuse(*steady, history)
    retry = fuse(*steady, history)
    assert first == retry
    assert list(history.steady) == [True]
    assert history.checked_in is False


def test_a_turn_with_no_signal_keeps_coach_after_two_steady_turns() -> None:
    # Same rule as before the refactor: 2 of the last 3 steady and nothing negative now.
    history = TurnHistory()
    steady = (face("happy", 0.6), words("joy", 0.8))
    turn(*steady, history)
    turn(*steady, history)
    assert turn({"status": "camera_off"}, None, history)["tone_mode"] == "coach"
