"""M4-15 with the real model: the pinned model and settings, judged on reviewed sentences.

This is a required gate. CI ("API gateway real-model safety gate") runs it inside the built
gateway image with RUN_MODEL_TESTS=1, HF_HUB_OFFLINE=1 and no network: it uses the model the
image already ships (Dockerfile) and fails if that model is missing.

- Every everyday sentence must stay quiet (false alarms are the risk this gate locks down).
- Every crisis phrasing must fire, except the known misses below (strict xfail).

Skipped without RUN_MODEL_TESTS=1, therefore the fast suite needs no model. On a laptop
(downloads the pinned model once):

    RUN_MODEL_TESTS=1 uv run pytest tests/test_crisis_meaning_model.py -q
"""

import os
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MODEL_TESTS") != "1",
    reason="set RUN_MODEL_TESTS=1 to download and run the real model",
)

HERE = Path(__file__).parent
MEANING = yaml.safe_load((HERE / "safety_meaning_cases.yaml").read_text())
EVERYDAY = [
    c["text"]
    for c in yaml.safe_load((HERE / "safety_cases.yaml").read_text())
    if c["expect"] == "none"
]


@pytest.fixture(scope="module")
def meaning():
    from app.config import Settings
    from app.crisis_meaning import CrisisMeaning, load_hf_embedder

    s = Settings()
    assert s.crisis_meaning_enabled, "the gate checks the layer as shipped: enabled"
    embedder = load_hf_embedder(
        s.crisis_meaning_model, s.crisis_meaning_revision, 128, local_files_only=False
    )
    return CrisisMeaning(
        threshold=s.crisis_meaning_threshold, margin=s.crisis_meaning_margin, embedder=embedder
    )


# Holdout phrasings the layer missed in the Nov 14 calibration. Kept as known misses
# (strict xfail): they record known gaps of a best-effort layer (README), and if a later
# model or example change catches one, this test fails until it moves to the must-fire list.
# Adding a miss here needs a reviewer's approval on the PR.
KNOWN_MISSES = {
    "I've written a note for my mum",
    "I can't see any way out except dying",
    "I keep picturing myself stepping in front of a train",  # the M3-07 rules catch this one
    "I've decided tonight is the night",
}
MUST_FIRE = [
    pytest.param(t, marks=pytest.mark.xfail(strict=True, reason="known miss, Nov 14"))
    if t in KNOWN_MISSES
    else t
    for t in (
        MEANING["dev"]["must_fire"]
        + MEANING["holdout"]["must_fire"]
        + MEANING["independent"]["must_fire"]
    )
]


@pytest.mark.parametrize("text", MUST_FIRE)
def test_missed_phrasing_fires(meaning, text: str) -> None:
    assert meaning.check(text) is not None, meaning.score(text)


@pytest.mark.parametrize(
    "text",
    MEANING["dev"]["must_not_fire"]
    + MEANING["holdout"]["must_not_fire"]
    + MEANING["independent"]["must_not_fire"]
    + EVERYDAY,
)
def test_everyday_sentence_stays_quiet(meaning, text: str) -> None:
    assert meaning.check(text) is None, meaning.score(text)
