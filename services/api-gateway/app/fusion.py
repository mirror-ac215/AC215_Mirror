"""Fusion (M3-06): the gated face reading + the text reading -> one context object per turn.

D-004: when face and words disagree, Mirror leans towards the more concerning signal and checks in,
gently. After a check-in it takes the patient's word for a while: it may ask again only once a
cooldown of N turns has passed and they still disagree (M4-17), never on back-to-back turns.

- Words that sound negative always lead: what the patient tells us outweighs what the camera sees.
- The face leads only where it has earned it. The M3-04 sweep on held-out video showed the gate is
  "ok" with useful precision only for neutral, happy and surprise; it is almost never right about
  angry, disgust, fear or sad. So a negative face never leads, but it still counts for
  `agreement`: a negative face with calm words is a "disagree" on purpose (the safe direction).
- agreement: "agree" / "disagree" when both signals count, otherwise "n/a". A disagreement within
  the cooldown after a check-in is sent as "n/a" with a note.
- tone_mode: "supportive" by default (MS1 feedback: no tough love for someone who may be struggling);
  "coach" only after 2 of the last 3 turns looked steady, and back to supportive on any negative turn.
- note: which signal this turn relied on (face / text / none) and how confident it was.

Usage, once per chat turn:

    context = fuse(visual, text, history)  # reads the history, changes nothing: safe to retry
    history.record(context, reply_delivered=True)  # once, when the turn's reply is final

A check-in starts the cooldown only if the patient actually saw it: `reply_delivered` is False
when the language model's reply was replaced (fixed medication or camera reply, LLM fallback) or
cut by the no-two-questions rule. Only finished, saved, non-crisis turns are recorded, so only
those advance the turn count.

Overlapping turns in one session: the orchestrator reserves a check-in as soon as fusion allows
one, with no await in between, so a second turn that starts before the first one is recorded sees
the reservation and does not check in too. `record()` keeps or drops the reservation; a turn that
ends without being recorded (the client left, a database error) calls `release_check_in()`.
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
ALREADY_CHECKED_IN = "; checked in recently"
CHECK_IN_IN_PROGRESS = "; check-in in progress in another reply"
# D-004 update (M4-17): turns from one check-in to the earliest next one. 2 is the minimum, so
# Mirror never checks in on back-to-back turns. The gateway sets it from
# FUSION_CHECKIN_COOLDOWN_TURNS (app/config.py).
DEFAULT_CHECKIN_COOLDOWN = 5


class TurnHistory:
    """Per session: whether each recent turn looked steady, and when Mirror last checked in."""

    def __init__(self, turns: int = 3, checkin_cooldown: int = DEFAULT_CHECKIN_COOLDOWN) -> None:
        if checkin_cooldown < 2:
            raise ValueError("checkin_cooldown must be at least 2: never check in back to back")
        self.steady: deque[bool] = deque(maxlen=turns)
        self.checkin_cooldown = checkin_cooldown
        self.turns = 0  # finished turns so far; the turn being fused now has this index
        self.last_check_in: int | None = None  # index of the turn that last checked in
        self.check_in_reserved = False  # a turn still streaming has a check-in under way

    @property
    def checked_in(self) -> bool:
        """Whether Mirror has checked in at all in this session."""
        return self.last_check_in is not None

    def may_check_in(self) -> bool:
        """True when the current turn may check in: none under way, and the cooldown has passed."""
        if self.check_in_reserved:
            return False
        return (
            self.last_check_in is None or self.turns - self.last_check_in >= self.checkin_cooldown
        )

    def reserve_check_in(self) -> None:
        """Hold the check-in for this turn, so an overlapping turn cannot check in as well."""
        self.check_in_reserved = True

    def release_check_in(self) -> None:
        """Drop a reservation for a turn that ended without being recorded."""
        self.check_in_reserved = False

    def record(self, context: dict, *, reply_delivered: bool) -> None:
        """Remember a finished turn. Call once per turn, after the reply is final.

        reply_delivered: the language model's reply reached the patient unchanged. A "disagree"
        turn counts as a check-in only then; otherwise the cooldown does not start. Either way the
        turn's reservation ends here (only the reserving turn has "disagree").
        """
        self.steady.append(_steady(_signals(context["visual"], context["text"])))
        if context["agreement"] == "disagree":
            self.check_in_reserved = False
            if reply_delivered:
                self.last_check_in = self.turns
        self.turns += 1


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

    Reads `history` but does not change it: call `history.record(context, ...)` once the turn is final.
    """
    text = text or NO_TEXT
    face, words = _signals(visual, text)
    face_label = face[0] if face else None
    text_label = words[0] if words else None

    note_extra = ""
    if face_label and text_label:
        both_negative = face_label in NEGATIVE and text_label in NEGATIVE
        agreement = "agree" if face_label == text_label or both_negative else "disagree"
        if agreement == "disagree" and not history.may_check_in():
            # D-004: trust them for a while, and never two check-ins at once
            pending = history.check_in_reserved
            agreement = "n/a"
            note_extra = CHECK_IN_IN_PROGRESS if pending else ALREADY_CHECKED_IN
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
