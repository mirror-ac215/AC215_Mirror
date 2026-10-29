"""Fusion (M3-06): the gated face reading + the text reading -> one context object per turn.

D-004: when face and words disagree, Mirror leans towards the more concerning signal and checks in
once, gently; after that it takes the patient's word and does not ask again.

- Words that sound negative always lead: what the patient tells us outweighs what the camera sees.
- The face leads only where it has earned it. The M3-04 sweep on held-out video showed the gate is
  "ok" with useful precision only for neutral, happy and surprise; it is almost never right about
  angry, disgust, fear or sad. So a negative face never leads, but it still counts for
  `agreement`: a negative face with calm words is a "disagree" on purpose (the safe direction).
- agreement: "agree" / "disagree" when both signals count, otherwise "n/a". Only the first
  disagreement in a session is sent as "disagree"; later ones are "n/a" with a note.
- tone_mode: "supportive" by default (MS1 feedback: no tough love for someone who may be struggling);
  "coach" only after 2 of the last 3 turns looked steady, and back to supportive on any negative turn.
- note: which signal this turn relied on (face / text / none) and how confident it was.

Usage, once per chat turn:

    context = fuse(visual, text, history)  # reads the history, changes nothing: safe to retry
    history.record(context)                # once, when the turn's reply is final
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
ALREADY_CHECKED_IN = "; already checked in this session"


class TurnHistory:
    """Per session: whether each recent turn looked steady, and whether Mirror already checked in."""

    def __init__(self, turns: int = 3) -> None:
        self.steady: deque[bool] = deque(maxlen=turns)
        self.checked_in = False

    def record(self, context: dict) -> None:
        """Remember a finished turn. Call once per turn, after the reply is final."""
        self.steady.append(_steady(_signals(context["visual"], context["text"])))
        if context["agreement"] == "disagree":
            self.checked_in = True


def common_label(label: str) -> str:
    """A text label in the camera's words (joy -> happy); camera labels pass through."""
    return TEXT_TO_FACE.get(label, label)


def _signals(visual: dict, text: dict) -> tuple[list | None, list | None]:
    """The face and text readings that count this turn, as [label, prob] in camera words, or None."""
    face = visual["top2"][0] if visual["status"] == "ok" else None
    top = text["top2"][0]
    words = [common_label(top[0]), top[1]] if top[1] >= MIN_TEXT_PROB else None
    return face, words


def _steady(signals: tuple[list | None, list | None]) -> bool:
    """A turn is steady when at least one signal counts and none of them is negative."""
    labels = [found[0] for found in signals if found]
    return bool(labels) and not any(label in NEGATIVE for label in labels)


def fuse(visual: dict, text: dict | None, history: TurnHistory, steady_needed: int = 2) -> dict:
    """The gate's `visual` block + the text module's block (None if unavailable) -> context object.

    Reads `history` but does not change it: call `history.record(context)` once the turn is final.
    """
    text = text or NO_TEXT
    face, words = _signals(visual, text)
    face_label = face[0] if face else None
    text_label = words[0] if words else None

    note_extra = ""
    if face_label and text_label:
        both_negative = face_label in NEGATIVE and text_label in NEGATIVE
        agreement = "agree" if face_label == text_label or both_negative else "disagree"
        if agreement == "disagree" and history.checked_in:
            agreement, note_extra = "n/a", ALREADY_CHECKED_IN  # D-004: ask once, then trust them
    else:
        agreement = "n/a"

    if text_label in NEGATIVE:
        main, (label, prob) = "text", words  # negative words always lead
    elif face_label in FACE_CAN_LEAD:
        main, (label, prob) = "face", face
    elif text_label:
        main, (label, prob) = "text", words
    elif face_label:
        main, (label, prob) = "face", face  # a negative face with no usable text: low trust
    else:
        main, label, prob = "none", None, None

    # This turn plus the previous ones, as if it were already recorded (last 3 in total).
    window = [*history.steady, _steady((face, words))][-history.steady.maxlen :]
    negative = any(found and found[0] in NEGATIVE for found in (face, words))
    coach = not negative and sum(window) >= steady_needed
    note = "main signal: none" if main == "none" else f"main signal: {main} ({label}, {prob:.2f})"
    return {
        "visual": visual,
        "text": text,
        "agreement": agreement,
        "tone_mode": "coach" if coach else "supportive",
        "note": note + note_extra,
    }
