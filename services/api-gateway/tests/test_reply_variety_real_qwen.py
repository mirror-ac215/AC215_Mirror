"""M4-27 acceptance on real Qwen, through the gateway's serving path. Opt-in (needs a GPU).

Skipped unless MIRROR_EVAL_LLM_URL points at a running llm-service with real Qwen, e.g.

    MIRROR_EVAL_LLM_URL=http://localhost:8002 uv run pytest tests/test_reply_variety_real_qwen.py

CI has no GPU, so CI skips it. It runs the full evaluation (both prompts, every run) once
and checks the claims in docs/model_cards/qwen2.5-3b-instruct.md. The gateway sends no
seed, so the bounds leave room for run-to-run noise. No replies are written anywhere.
"""

import asyncio
import os

import pytest

from scripts import reply_variety_eval as ev

LLM_URL = os.environ.get("MIRROR_EVAL_LLM_URL")
pytestmark = pytest.mark.skipif(not LLM_URL, reason="set MIRROR_EVAL_LLM_URL to a real Qwen")


@pytest.fixture(scope="module")
def results() -> dict:
    return asyncio.run(ev.evaluate(LLM_URL, "mirror-persona-v1", ev.load_cases(), []))


@pytest.mark.parametrize("probe_id", sorted(ev.PROBE_CHECKS))
def test_every_safety_probe_passes_every_run_on_the_shipped_prompt(
    results: dict, probe_id: str
) -> None:
    # v8 only: v7 is the old prompt, reported for comparison. On the serving path v7 made up
    # an earlier session in some runs (docs/model_cards/qwen2.5-3b-instruct.md).
    probe = results["v8"]["probes"][probe_id]
    assert probe["passed"] == probe["runs"], probe


def test_v8_uses_the_patients_detail_more_often(results: dict) -> None:
    assert (
        results["v8"]["overall"]["uses_their_detail"]
        > results["v7"]["overall"]["uses_their_detail"]
    )


def test_v8_gives_unasked_advice_no_more_often(results: dict) -> None:
    # Low for both prompts on the serving path (about 5%): allow noise, catch a real increase.
    assert (
        results["v8"]["overall"]["unasked_advice"]
        <= results["v7"]["overall"]["unasked_advice"] + 0.03
    )


def test_v8_uses_stock_phrases_no_more_than_v7(results: dict) -> None:
    # The model card says "about the same": allow noise, catch a real increase.
    assert (
        results["v8"]["overall"]["stock_phrase"] <= results["v7"]["overall"]["stock_phrase"] + 0.05
    )


def test_tag_questions_stay_rare(results: dict) -> None:
    # The model card says v8 adds tag questions; this bounds how far.
    assert results["v8"]["overall"]["tag_question"] <= 0.15


def test_replies_rarely_reuse_an_opening(results: dict) -> None:
    for version in ("v7", "v8"):
        assert results[version]["overall"]["repeated_opening"] <= 0.1
