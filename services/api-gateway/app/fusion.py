"""Fusion (M3-06): the gated face reading + the text reading -> one context object per turn.

The face leads only where it has earned it. The M3-04 sweep on held-out video showed the gate is
"ok" with useful precision only for neutral, happy and surprise; it is almost never right about
angry, disgust, fear or sad. So for those emotions the face may agree with the words, but it never
leads (D-004: the more concerning signal is not ignored; when face and words disagree the prompt asks
the patient instead of picking one).

- agreement: "agree" / "disagree" when both signals count, otherwise "n/a".
- tone_mode: "supportive" by default (MS1 feedback: no tough love for someone who may be struggling);
  "coach" only after 2 of the last 3 turns looked steady, and back to supportive on any negative turn.
- note: which signal this turn relied on (face / text / none) and how confident it was.
"""

from __future__ import annotations

from collections import deque

# The text model (D-003) and the camera model name the same 7 emotions differently.
TEXT_TO_FACE = {"anger": "angry", "joy": "happy", "sadness": "sad"}
NEGATIVE = {"angry", "disgust", "fear", "sad"}
FACE_CAN_LEAD = {"neutral", "happy", "surprise"}  # M3-04 sweep: the only reliable face readings
MIN_TEXT_PROB = 0.40  # same bar as the prompt template (M3-08)
# When the text module is unavailable: the contract requires a text block; probability 0 makes
# the prompt treat it as "unclear", so the turn continues without text-emotion context.
NO_TEXT = {"top2": [["neutral", 0.0]]}


class TurnHistory:
    """Per session: whether each recent turn looked steady (calm or positive, nothing negative)."""

    def __init__(self, turns: int = 3) -> None:
        self.steady: deque[bool] = deque(maxlen=turns)


def common_label(label: str) -> str:
    """A text label in the camera's words (joy -> happy); camera labels pass through."""
    return TEXT_TO_FACE.get(label, label)


def fuse(visual: dict, text: dict | None, history: TurnHistory, steady_needed: int = 2) -> dict:
    """The gate's `visual` block + the text module's block (None if unavailable) -> context object."""
    text = text or NO_TEXT
    face = visual["top2"][0] if visual["status"] == "ok" else None  # [label, prob] or None
    words = text["top2"][0] if text["top2"][0][1] >= MIN_TEXT_PROB else None
    face_label = face[0] if face else None
    text_label = common_label(words[0]) if words else None

    if face_label and text_label:
        both_negative = face_label in NEGATIVE and text_label in NEGATIVE
        agreement = "agree" if face_label == text_label or both_negative else "disagree"
    else:
        agreement = "n/a"

    if face_label in FACE_CAN_LEAD:
        main, label, prob = "face", face_label, face[1]
    elif text_label:
        main, label, prob = "text", text_label, words[1]
    elif face_label:
        main, label, prob = "face", face_label, face[1]  # a negative face with no usable text: low trust
    else:
        main, label, prob = "none", None, None

    signals = [found for found in (face_label, text_label) if found]
    negative = any(found in NEGATIVE for found in signals)
    history.steady.append(bool(signals) and not negative)
    coach = not negative and sum(history.steady) >= steady_needed
    note = "main signal: none" if main == "none" else f"main signal: {main} ({label}, {prob:.2f})"
    return {
        "visual": visual,
        "text": text,
        "agreement": agreement,
        "tone_mode": "coach" if coach else "supportive",
        "note": note,
    }
