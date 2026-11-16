"""Second safety layer (M4-15): crisis by meaning, not by exact wording.

The M3-07 rules (app/safety.py) match the phrasings they list. Each new round of
review found wording they miss, e.g. "I wish I could just disappear". This layer
compares the message with a reviewed list of crisis examples by meaning, using a
small sentence-embedding model on CPU, and fires when the message is close to one.

How it decides:
- Every example and the message become unit vectors; similarity is their dot
  product (cosine), from -1 to 1.
- crisis = the highest similarity to a CRISIS_EXAMPLES sentence.
- safe = the highest similarity to a SAFE_EXAMPLES sentence (everyday figures of
  speech: "this commute is killing me", "I could disappear into bed all weekend").
- It fires when crisis >= threshold AND crisis - safe >= margin. The margin keeps
  everyday hyperbole quiet even when it shares words with a crisis example.

Design notes:
- The rules stay the first layer: fast, auditable, and they run first. This layer
  runs only when the rules did not already say crisis, and either one firing
  means crisis (the gateway withholds the reply, shows 988, flags the clinician).
- If the model cannot load, this layer is off and the rules still run. It never
  blocks a turn and never decides that a message is safe.
- The examples here are not the test phrasings: tests/safety_meaning_cases.yaml
  holds different wording, therefore the tests measure generalisation, not recall
  of the list.
- The embedder is injectable: unit tests use a small fake and need no model.
- Never log the message text: only the example id that matched.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

logger = logging.getLogger("mirror")

# A list of texts in, one unit-length vector per text out.
Embedder = Callable[[Sequence[str]], list[list[float]]]

# Reviewed crisis examples: (id, sentence). The id is what logs and metrics show.
# Short, plain, first person. Change only with a review and the calibration in the README.
CRISIS_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("disappear", "I want to vanish and never come back"),
    ("not-exist", "I wish I had never been born"),
    ("no-reason", "I can't think of a single reason to keep living"),
    ("no-future", "I don't see any future for myself at all"),
    ("burden", "my family would be better off if I wasn't around"),
    ("burden-2", "I'm just a burden and people would be relieved if I was gone"),
    ("not-wake", "I hope I don't wake up tomorrow morning"),
    ("sleep-forever", "I just want to go to sleep forever"),
    ("overdose", "I'm planning to swallow the whole bottle of pills"),
    ("overdose-2", "I've been saving up my tablets to take them all at once"),
    ("method", "I've been looking up ways to kill myself"),
    ("plan", "I have worked out how and when I'm going to do it"),
    ("goodbye", "I wanted to say goodbye to everyone before I go"),
    ("giving-away", "I've started giving my things away because I won't need them"),
    ("end-pain", "dying is the only way to make the pain stop"),
    ("give-up-life", "I'm done with life and I want out"),
    ("self-harm", "I hurt myself on purpose last night to feel something"),
    ("self-harm-urge", "I really want to cut myself right now"),
    ("hopeless", "nothing will ever get better so there's no point in going on"),
    ("harm-other", "I'm going to hurt someone, I can't control it anymore"),
    ("crash", "I think about crashing my car on purpose"),
    ("final-letter", "I've written a letter for when I'm gone"),
    ("not-around", "I won't be around much longer"),
)

# Everyday sentences that share words with crisis examples but are not a crisis.
SAFE_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("hyperbole-kill", "this commute is killing me"),
    ("hyperbole-dead", "I'm dead tired after the gym"),
    ("hyperbole-die", "I nearly died laughing at that video"),
    ("disappear-bed", "I could disappear into my bed all weekend"),
    ("vanish-holiday", "I want to vanish to a beach for a week"),
    ("sleep-in", "I want to sleep in all day on Saturday"),
    ("pills-routine", "I took my vitamins with breakfast"),
    ("goodbye-move", "I said goodbye to my colleagues before moving cities"),
    ("give-away-clothes", "I'm giving my old clothes away to charity"),
    ("done-work", "I'm done with this project and I want out of the meeting"),
    ("cut-hair", "I want to cut my hair short"),
    ("hurt-sport", "I hurt my knee playing football"),
    ("no-point-meeting", "there's no point in going to that meeting"),
    ("future-job", "I don't see a future in this job"),
    ("wish-era", "I wish I'd grown up in a different decade"),
    ("injury", "I injured my shoulder at the gym"),
    ("routine-meds", "I took my medication on time this morning"),
    ("busy-life", "I want my schedule to calm down"),
    ("diet", "I'm cutting sugar out of my diet"),
    ("sleep-tired", "I'm so tired I could sleep through the weekend"),
    ("letter-friend", "I wrote a card for my friend's birthday"),
    ("drive-trip", "I keep thinking about driving to the mountains"),
)


class CrisisMeaningUnavailable(RuntimeError):
    """The model could not load or run. The rules still run on their own.

    `stage` is "load" (the model or examples never loaded) or "inference" (one message
    could not be scored): logs and metrics report it, never the message.
    """

    def __init__(self, detail: str, stage: str = "load") -> None:
        super().__init__(detail)
        self.stage = stage


@dataclass(frozen=True)
class MeaningScore:
    crisis: float  # highest similarity to a crisis example
    safe: float  # highest similarity to a safe example
    crisis_id: str  # which crisis example was closest


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def load_hf_embedder(
    model_name: str, revision: str, max_tokens: int, local_files_only: bool = True
) -> Embedder:
    """Mean-pooled, unit-length sentence vectors from a Hugging Face model (CPU).

    Imported here, not at the top: torch/transformers load only when needed.
    Serving uses the reviewed local cache only (local_files_only=True).
    """
    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        model_name, revision=revision, local_files_only=local_files_only
    )
    model = AutoModel.from_pretrained(
        model_name, revision=revision, local_files_only=local_files_only
    )
    model.eval()

    def embed(texts: Sequence[str]) -> list[list[float]]:
        batch = tokenizer(
            list(texts), padding=True, truncation=True, max_length=max_tokens, return_tensors="pt"
        )
        with torch.no_grad():
            hidden = model(**batch).last_hidden_state
        mask = batch["attention_mask"].unsqueeze(-1).float()
        pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return torch.nn.functional.normalize(pooled, dim=1).tolist()

    return embed


class CrisisMeaning:
    """Loads the model once, embeds the examples once, then scores messages."""

    def __init__(
        self,
        threshold: float,
        margin: float,
        model_name: str = "sentence-transformers/all-mpnet-base-v2",
        revision: str = "main",
        max_chars: int = 2000,
        max_tokens: int = 128,
        embedder: Embedder | None = None,
        crisis_examples: Sequence[tuple[str, str]] = CRISIS_EXAMPLES,
        safe_examples: Sequence[tuple[str, str]] = SAFE_EXAMPLES,
    ) -> None:
        self.threshold = threshold
        self.margin = margin
        self.model_name = model_name
        self.revision = revision
        self.max_chars = max_chars
        self.max_tokens = max_tokens
        self._embedder = embedder
        self._crisis_examples = tuple(crisis_examples)
        self._safe_examples = tuple(safe_examples)
        self._crisis_vectors: list[list[float]] | None = None
        self._safe_vectors: list[list[float]] | None = None
        self._failed = False  # a failed load is not retried on every message
        self._lock = threading.Lock()

    def _ready(self) -> Embedder:
        if self._failed:
            raise CrisisMeaningUnavailable("model failed to load earlier")
        if self._crisis_vectors is None:
            with self._lock:
                if self._crisis_vectors is None:
                    start = time.perf_counter()
                    try:
                        if self._embedder is None:
                            self._embedder = load_hf_embedder(
                                self.model_name, self.revision, self.max_tokens
                            )
                        self._crisis_vectors = self._embedder([t for _, t in self._crisis_examples])
                        self._safe_vectors = self._embedder([t for _, t in self._safe_examples])
                    except Exception as exc:  # any load failure: rules only
                        self._failed = True
                        logger.error(
                            "crisis_meaning_load_failed", extra={"error_type": type(exc).__name__}
                        )
                        raise CrisisMeaningUnavailable(str(exc)) from exc
                    logger.info(
                        "crisis_meaning_loaded",
                        extra={"load_ms": round((time.perf_counter() - start) * 1000)},
                    )
        assert self._embedder is not None
        return self._embedder

    def warm_up(self) -> None:
        """Load the model and embed the examples before the first patient message."""
        self.score("warm-up message")

    def score(self, message: str) -> MeaningScore:
        embed = self._ready()
        try:
            (vector,) = embed([message[: self.max_chars]])
        except Exception as exc:
            raise CrisisMeaningUnavailable(str(exc), stage="inference") from exc
        assert self._crisis_vectors is not None and self._safe_vectors is not None
        crisis_sims = [_dot(vector, v) for v in self._crisis_vectors]
        best = max(range(len(crisis_sims)), key=crisis_sims.__getitem__)
        safe = max((_dot(vector, v) for v in self._safe_vectors), default=-1.0)
        return MeaningScore(
            crisis=crisis_sims[best], safe=safe, crisis_id=self._crisis_examples[best][0]
        )

    def check(self, message: str) -> str | None:
        """The rule id to report ("meaning-<example id>") when it fires, else None."""
        s = self.score(message)
        if s.crisis >= self.threshold and s.crisis - s.safe >= self.margin:
            return f"meaning-{s.crisis_id}"
        return None


_instance: CrisisMeaning | None = None
_built = False
_instance_lock = threading.Lock()


def get_crisis_meaning() -> CrisisMeaning | None:
    """One shared instance, configured from env vars once; None when switched off."""
    global _instance, _built
    if not _built:
        with _instance_lock:
            if not _built:
                from app.config import Settings

                settings = Settings()
                if settings.crisis_meaning_enabled:
                    _instance = CrisisMeaning(
                        threshold=settings.crisis_meaning_threshold,
                        margin=settings.crisis_meaning_margin,
                        model_name=settings.crisis_meaning_model,
                        revision=settings.crisis_meaning_revision,
                    )
                _built = True
    return _instance
