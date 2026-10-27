"""Smoothing and gating of the camera signal (M3-04).

cv-service scores every frame on its own, so single readings jump around
(sad, neutral, sad, happy...). This module keeps a short window of recent frame
results per session and turns it into one honest summary: the `visual` block
of the context object (docs/contracts/context_object.schema.json).

- camera_off: the patient did not consent to the camera.
- dropped:    not enough frames with a face to say anything.
- uncertain:  enough frames, but the average reading is weak, close or unsteady.
- ok:         a confident, steady reading.

Frames themselves are never kept, only cv-service's probabilities.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from app.config import Settings

# The 7 labels cv-service returns (docs/contracts/cv-service.openapi.yaml).
FACE_LABELS = ("angry", "disgust", "fear", "happy", "neutral", "sad", "surprise")


@dataclass(frozen=True)
class FrameReading:
    """One cv-service result for one frame, without the image."""

    ts: float  # seconds (time.monotonic()) when the gateway received the frame
    face_found: bool
    probs: dict[str, float]  # the 7 emotion probabilities; empty when no face was found


class FrameWindow:
    """The most recent frame readings for one session, with bounded memory."""

    def __init__(self, max_frames: int) -> None:
        # A deque with maxlen drops the oldest reading automatically when full.
        self._readings: deque[FrameReading] = deque(maxlen=max_frames)

    def add(self, reading: FrameReading) -> None:
        self._readings.append(reading)

    def recent(self, now: float, window_s: float) -> list[FrameReading]:
        """Readings from the last `window_s` seconds, oldest first."""
        return [r for r in self._readings if now - r.ts <= window_s]


def _usable(reading: FrameReading) -> bool:
    """A face with all 7 labels, each a real number between 0 and 1.

    Anything else (missing or unknown labels, NaN, text, a bool) counts as a frame
    without a face, so a broken cv-service reply leads to "dropped", never a crash.
    """
    probs = reading.probs
    return (
        reading.face_found
        and isinstance(probs, dict)
        and set(probs) == set(FACE_LABELS)
        and all(
            isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(p) and 0 <= p <= 1
            for p in probs.values()
        )
    )


def _top_label(probs: dict[str, float]) -> str:
    """The emotion with the highest probability in one reading."""
    return max(probs, key=lambda label: probs[label])


def gate(readings: list[FrameReading], settings: Settings, camera_on: bool) -> dict:
    """Recent frame readings in, the context object's `visual` block out.

    `readings` should already be limited to the time window (FrameWindow.recent).
    """
    if not camera_on:
        return {"status": "camera_off"}

    n_frames = len(readings)
    with_face = [r for r in readings if _usable(r)]
    face_ratio = len(with_face) / n_frames if n_frames else 0.0

    # 1. Enough evidence? Too few faces means we say nothing about the face.
    if len(with_face) < settings.gate_min_frames or face_ratio < settings.gate_min_face_ratio:
        return {"status": "dropped", "window_s": settings.gate_window_s, "n_frames": n_frames}

    # 2. Smooth: average each emotion's probability over the frames with a face.
    #    Every usable reading has all 7 labels, so the ranking always has a second place.
    average = {
        label: sum(r.probs[label] for r in with_face) / len(with_face) for label in FACE_LABELS
    }
    ranked = sorted(average.items(), key=lambda item: item[1], reverse=True)
    (top, top_p), (second, second_p) = ranked[0], ranked[1]

    # 3. Stability: in what share of frames was the averaged top emotion also
    #    that frame's own top emotion? 1.0 = every frame agreed.
    stability = sum(1 for r in with_face if _top_label(r.probs) == top) / len(with_face)

    # 4. Gate: "ok" only when the reading is strong, clearly ahead, and steady.
    confident = (
        top_p >= settings.gate_min_top_prob
        and top_p - second_p >= settings.gate_min_margin
        and stability >= settings.gate_min_stability
    )
    return {
        "status": "ok" if confident else "uncertain",
        "top2": [[top, round(top_p, 3)], [second, round(second_p, 3)]],
        "stability": round(stability, 2),
        "window_s": settings.gate_window_s,
        "n_frames": n_frames,
    }