"""Text-emotion module (M3-05).

Turns one chat message into the two most likely emotions with their
probabilities, in the shape the context object expects for `text.top2`:

    [["sadness", 0.71], ["fear", 0.12]]

The model is the one chosen in M2-11 (decision D-003 in docs/decisions.md):
j-hartmann/emotion-english-distilroberta-base. It already outputs Mirror's
7 labels, the same 7 the camera model uses: face and text can be compared.

Design notes (useful for the oral check):
- The model is loaded lazily, on the first message or on warm_up(), not at
  import time. Importing this file costs nothing: tests and the rest of
  the gateway don't need torch or a model download.
- The classifier is injectable. Unit tests pass a small fake function and
  run in milliseconds in CI with no network.
- The crisis check (M3-07) runs before this module, and never depends on it:
  this module only describes tone, it never decides safety.
- We never log the message text (team rule: no real user text in logs),
  only the labels, scores and latency.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("mirror")

# Mirror's 7 emotion labels: the same names as the camera model and the contract.
LABELS: tuple[str, ...] = (
    "anger",
    "disgust",
    "fear",
    "joy",
    "neutral",
    "sadness",
    "surprise",
)

# A classifier takes a message and returns a score for every label.
# The real one wraps a Hugging Face pipeline; tests use a fake.
Classifier = Callable[[str], dict[str, float]]


class TextEmotionUnavailable(RuntimeError):
    """The model could not be loaded or run. The gateway falls back to
    text-only replies without an emotion signal (fallback paths: M4-04)."""


@dataclass(frozen=True)
class TextEmotionResult:
    """What the gateway gets back for one message."""

    top2: list[list[str | float]]  # [[label, prob], [label, prob]], most likely first
    latency_ms: float
    model: str

    def as_context(self) -> dict:
        """The `text` block of the context object (docs/contracts/context_object.schema.json)."""
        return {"top2": self.top2}


def top2_from_scores(scores: dict[str, float]) -> list[list[str | float]]:
    """Pick the two highest scores, rounded to 3 decimals, most likely first.

    Raises ValueError if the model returned a label Mirror doesn't know: a
    wrong or swapped model fails loudly instead of sending odd labels downstream.
    """
    unknown = set(scores) - set(LABELS)
    if unknown:
        raise ValueError(f"Unexpected emotion labels from the model: {sorted(unknown)}")
    if not scores:
        raise ValueError("The model returned no scores")
    # NaN or infinity would sort unpredictably and break the JSON sent downstream:
    # only finite real numbers count as a score (bool is excluded on purpose).
    for label, score in scores.items():
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
        ):
            raise ValueError(f"Non-finite or non-numeric score for {label!r}")

    # Sort by score (highest first); ties broken by label name for stable results.
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [[label, round(min(max(score, 0.0), 1.0), 3)] for label, score in ranked[:2]]


def load_hf_classifier(model_name: str, revision: str, max_tokens: int) -> Classifier:
    """Build the real classifier from the Hugging Face pipeline (CPU).

    Imported here, not at the top: torch/transformers load only when the
    model is actually needed.
    """
    from transformers import pipeline

    clf = pipeline(
        "text-classification",
        model=model_name,
        revision=revision,
        top_k=None,  # return scores for all 7 labels, not just the best one
        device=-1,  # -1 = CPU
    )

    def classify(text: str) -> dict[str, float]:
        output = clf(text, truncation=True, max_length=max_tokens)
        # The pipeline returns [[{label, score}, ...]] for one input; unwrap it.
        if output and isinstance(output[0], list):
            output = output[0]
        return {item["label"]: float(item["score"]) for item in output}

    return classify


class TextEmotion:
    """Loads the classifier once and scores messages with it."""

    def __init__(
        self,
        model_name: str = "j-hartmann/emotion-english-distilroberta-base",
        revision: str = "0e1cd914e3d46199ed785853e12b57304e04178b",
        max_chars: int = 2000,
        max_tokens: int = 256,
        classifier: Classifier | None = None,
    ) -> None:
        self.model_name = model_name
        self.revision = revision
        self.max_chars = max_chars
        self.max_tokens = max_tokens
        self._classifier = classifier
        # Two requests arriving at once must not load the model twice.
        self._lock = threading.Lock()

    def _get_classifier(self) -> Classifier:
        if self._classifier is None:
            with self._lock:
                if self._classifier is None:
                    start = time.perf_counter()
                    try:
                        self._classifier = load_hf_classifier(
                            self.model_name, self.revision, self.max_tokens
                        )
                    except Exception as exc:  # any load failure means "no text signal"
                        logger.error("text_emotion_load_failed", extra={"error": str(exc)})
                        raise TextEmotionUnavailable(str(exc)) from exc
                    logger.info(
                        "text_emotion_loaded",
                        extra={"load_ms": round((time.perf_counter() - start) * 1000)},
                    )
        return self._classifier

    def warm_up(self) -> None:
        """Load the model and run it once; the first patient message is then fast."""
        self.analyse("warm-up message")

    def analyse(self, message: str) -> TextEmotionResult:
        """Message in, top-2 emotions + probabilities out."""
        text = message.strip()[: self.max_chars]
        start = time.perf_counter()

        if not text:
            # Nothing to read (the API already rejects empty messages; this is a safety net).
            top2: list[list[str | float]] = [["neutral", 1.0]]
        else:
            classifier = self._get_classifier()
            try:
                scores = classifier(text)
            except Exception as exc:
                raise TextEmotionUnavailable(str(exc)) from exc
            try:
                top2 = top2_from_scores(scores)
            except (ValueError, TypeError, AttributeError) as exc:
                # Malformed output (no scores, unknown labels, not a dict) takes the same
                # text-only fallback as a crash: the chat turn continues without text emotion.
                logger.error("text_emotion_bad_output", extra={"error": str(exc)})
                raise TextEmotionUnavailable(str(exc)) from exc

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "text_emotion",
            extra={"top1": top2[0][0], "latency_ms": latency_ms},
        )
        return TextEmotionResult(top2=top2, latency_ms=latency_ms, model=self.model_name)


_instance: TextEmotion | None = None
# Guards the first call: two requests arriving together must share one instance
# (and therefore one model load), not build two.
_instance_lock = threading.Lock()


def get_text_emotion() -> TextEmotion:
    """One shared instance for the whole gateway, configured from env vars."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:  # checked again: another thread may have built it meanwhile
                from app.config import Settings

                settings = Settings()
                _instance = TextEmotion(
                    model_name=settings.text_emotion_model,
                    revision=settings.text_emotion_revision,
                    max_chars=settings.text_emotion_max_chars,
                )
    return _instance
