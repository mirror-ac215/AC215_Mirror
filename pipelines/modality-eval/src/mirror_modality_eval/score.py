"""Score face, text and combined readings against the IEMOCAP labels.

Input is one row per utterance with:
  label        Mirror label from the IEMOCAP table (text names), "" for frustration
  text_label   the text model's top label, text names
  text_prob    its probability
  face_label   the camera's top label, camera names (angry, happy, sad, ...)
  face_status  "ok" when the gate passed, anything else when it did not

A reading "counts" only when it passes its bar: text at MIN_TEXT_PROB, face at status "ok".
This mirrors the rule in fusion.py, where a face reading that did not pass the gate is ignored.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from mirror_modality_eval import FACE_TO_MIRROR, MIN_TEXT_PROB, SCORED

Z = 1.96  # 95% interval


def wilson(successes: int, n: int) -> tuple[float, float]:
    """95% interval for a share; same formula as the fairness audit (M3-02)."""
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    centre = (p + Z * Z / (2 * n)) / (1 + Z * Z / n)
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass(frozen=True)
class Row:
    label: str
    text_label: str
    text_prob: float
    face_label: str
    face_status: str

    @classmethod
    def from_dict(cls, d: dict) -> Row:
        return cls(
            label=d["label"],
            text_label=d["text_label"],
            text_prob=float(d["text_prob"]),
            face_label=d["face_label"],
            face_status=d["face_status"],
        )

    def text_reading(self) -> str | None:
        """The text label if it passes the bar, else None."""
        return self.text_label if self.text_prob >= MIN_TEXT_PROB else None

    def face_reading(self) -> str | None:
        """The face label in Mirror names if the gate passed, else None."""
        if self.face_status != "ok":
            return None
        return FACE_TO_MIRROR.get(self.face_label, self.face_label)

    def combined_reading(self) -> str | None:
        """Text when it counts, otherwise the face. A plain rule, not the gateway's fusion."""
        return self.text_reading() or self.face_reading()


MODES = {
    "face": Row.face_reading,
    "text": Row.text_reading,
    "both": Row.combined_reading,
}


def score_mode(rows: Iterable[Row], mode: str) -> dict:
    """Accuracy on the four scored labels, among the rows where this mode gives a reading."""
    rows = [r for r in rows if r.label in SCORED]
    reader = MODES[mode]
    counted = [(r, reader(r)) for r in rows if reader(r) is not None]
    hits = sum(1 for r, pred in counted if pred == r.label)
    low, high = wilson(hits, len(counted))
    return {
        "scored_rows": len(rows),
        "counted": len(counted),
        "coverage": len(counted) / len(rows) if rows else 0.0,
        "accuracy": hits / len(counted) if counted else 0.0,
        "low": low,
        "high": high,
    }


def beyond_noise(a: dict, b: dict) -> bool:
    """A gap counts only when the two intervals do not overlap."""
    return a["low"] > b["high"] or b["low"] > a["high"]


def score_overlap(rows: Iterable[Row]) -> dict:
    """Face and text on the same rows: only those where both give a reading.

    score_mode scores each mode on its own subset, which differ; this is the like-for-like view.
    """
    both = [
        r
        for r in rows
        if r.label in SCORED and r.face_reading() is not None and r.text_reading() is not None
    ]
    result = {"rows": len(both)}
    for mode in ("face", "text"):
        reader = MODES[mode]
        hits = sum(1 for r in both if reader(r) == r.label)
        low, high = wilson(hits, len(both))
        result[mode] = {"accuracy": hits / len(both) if both else 0.0, "low": low, "high": high}
    result["agree_share"] = (
        sum(1 for r in both if r.face_reading() == r.text_reading()) / len(both) if both else 0.0
    )
    result["face_vs_text_beyond_noise"] = beyond_noise(result["face"], result["text"])
    return result


def compare(rows: list[Row]) -> dict:
    """Face, text and combined scores for the four labels, the face vs text gap, and the overlap."""
    result = {mode: score_mode(rows, mode) for mode in MODES}
    result["face_vs_text_beyond_noise"] = beyond_noise(result["face"], result["text"])
    result["overlap"] = score_overlap(rows)
    return result


def frustration_reads(rows: list[Row]) -> dict:
    """What each signal reads for frustration rows. Not scored: there is no Mirror label for it."""
    frust = [r for r in rows if r.label == ""]  # frustration rows have an empty label
    text = Counter(r.text_reading() or "none" for r in frust)
    face = Counter(r.face_reading() or "none" for r in frust)
    return {"rows": len(frust), "text": dict(text), "face": dict(face)}
