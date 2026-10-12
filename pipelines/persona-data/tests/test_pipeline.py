import csv
import json
from pathlib import Path

import pytest
import yaml

from mirror_persona_data.pipeline import Pair, clean, read_pairs, run

PARAMS = yaml.safe_load((Path(__file__).parents[1] / "params.yaml").read_text())
GOOD = "Start by making your bed and tidying one small corner of your room today."


def _write(path: Path, rows: list[tuple[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["question", "answer", "a_len", "formatted", "q_len"])
        writer.writerows([(q, a, len(a), "### Instruction: ...", len(q)) for q, a in rows])


@pytest.mark.parametrize("response", [
    "I am Dr. Smith and I think you should rest.",
    "As a clinical psychologist, I would say this is common.",
    "I'm a licensed therapist, so trust me on this one point.",
    "In my clinical practice I have seen this many times before.",
    "Many of my patients describe exactly this feeling of dread.",
    # first row of the real data (jbp_clean_full.csv)
    "I am a psychology professor at the University of Toronto, a clinical psychologist, "
    "and an author.",
    "When I wrote 12 Rules for Life I was thinking about exactly this.",
])
def test_identity_claims_are_removed(response):
    kept, removed = clean([Pair("f.csv:2", "How do I cope?", response)], PARAMS)
    assert kept == []
    assert removed[0]["reason"].startswith("identity:")


@pytest.mark.parametrize("response", [
    GOOD,
    "It might help to talk to a clinical psychologist about how often this happens.",
])
def test_plain_advice_is_kept(response):
    kept, removed = clean([Pair("f.csv:2", "Where do I start?", response)], PARAMS)
    assert [p.response for p in kept] == [response]
    assert removed == []


def test_whitespace_and_case_duplicates_are_removed():
    pairs = [Pair("a:2", "Hi", GOOD), Pair("a:3", "hi ", "  " + GOOD.upper())]
    kept, removed = clean(pairs, PARAMS)
    assert len(kept) == 1
    assert removed[0]["reason"] == "duplicate"


def test_empty_and_short_are_removed():
    kept, removed = clean([Pair("a:2", "Q", ""), Pair("a:3", "Q", "Yes.")], PARAMS)
    assert kept == []
    assert [r["reason"] for r in removed] == ["empty", "too_short"]


def test_missing_column_gives_clear_error(tmp_path):
    (tmp_path / "x.csv").write_text("question,answer\nq,a\n")
    with pytest.raises(ValueError, match="missing columns"):
        read_pairs(tmp_path, "*.csv", "prompt", "response")


def test_run_is_reproducible_and_reports_counts(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    rows = [(f"Question {i}?", f"{GOOD} Step {i}.") for i in range(20)]
    rows += [("Who are you?", "As a clinical psychologist I see this a lot in people.")]
    _write(raw / "jbp_clean_full.csv", rows)
    _write(raw / "jbp_train.csv", rows[:5])  # old split file: must be ignored

    first = run(raw, tmp_path / "out1", PARAMS)
    second = run(raw, tmp_path / "out2", PARAMS)

    assert first["split_sha256"] == second["split_sha256"]
    assert first["pairs_in"] == 21 and first["pairs_out"] == 20
    assert first["removed_by_reason"] == {"identity:clinical_role": 1}
    assert sum(first["split_counts"].values()) == 20
    saved = json.loads((tmp_path / "out1" / "report.json").read_text())
    assert saved == first
