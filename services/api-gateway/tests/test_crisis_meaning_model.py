"""M4-15 with the real model: the misses fire, everyday sentences stay quiet.

Skipped by default (it needs the model). Run it on your laptop:

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
    embedder = load_hf_embedder(
        s.crisis_meaning_model, s.crisis_meaning_revision, 128, local_files_only=False
    )
    return CrisisMeaning(
        threshold=s.crisis_meaning_threshold, margin=s.crisis_meaning_margin, embedder=embedder
    )


# Holdout phrasings the layer missed in the Nov 14 calibration. Kept as known misses
# (strict xfail): if a later model or example change catches one, this test says so.
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
    for t in MEANING["dev"]["must_fire"] + MEANING["holdout"]["must_fire"]
]


@pytest.mark.parametrize("text", MUST_FIRE)
def test_missed_phrasing_fires(meaning, text: str) -> None:
    assert meaning.check(text) is not None, meaning.score(text)


@pytest.mark.parametrize(
    "text",
    MEANING["dev"]["must_not_fire"] + MEANING["holdout"]["must_not_fire"] + EVERYDAY,
)
def test_everyday_sentence_stays_quiet(meaning, text: str) -> None:
    assert meaning.check(text) is None, meaning.score(text)
