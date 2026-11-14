import re

import pytest

from mirror_pairwise import PAIRS
from mirror_pairwise.pairwise import build, tally, wilson

PROMPTS = [
    {"prompt_id": f"p{i}", "prompt": f"q{i}",
     "replies": {"base": f"b{i}", "lora": f"l{i}", "lora_visual": f"v{i}"}}
    for i in range(4)
]


def test_every_pair_for_every_prompt():
    visible, key = build(PROMPTS, seed=1)
    assert len(visible) == len(PROMPTS) * len(PAIRS)
    assert len(key) == len(visible)


def test_key_maps_back_to_the_right_replies():
    visible, key = build(PROMPTS, seed=2)
    by_id = {row["comparison_id"]: row for row in visible}
    for cid, info in key.items():
        expected = PROMPTS[int(info["prompt_id"][1:])]["replies"]
        assert by_id[cid]["reply_a"] == expected[info["A"]]
        assert by_id[cid]["reply_b"] == expected[info["B"]]


def test_visible_rows_hide_model_names():
    visible, _ = build(PROMPTS, seed=3)
    for row in visible:
        assert set(row) == {"comparison_id", "prompt", "camera", "reply_a", "reply_b"}
        assert "pair" not in row and "A" not in row


def test_no_visible_field_contains_a_model_name():
    names = {name for pair in PAIRS for name in pair}
    visible, _ = build(PROMPTS, seed=9)
    for row in visible:
        for field, value in row.items():
            assert not any(name in str(value) for name in names), (field, value)


def test_comparison_ids_are_opaque_and_unique():
    visible, key = build(PROMPTS, seed=10)
    ids = [row["comparison_id"] for row in visible]
    assert len(set(ids)) == len(ids) == len(key)
    for cid in ids:
        assert re.fullmatch(r"c\d{4}", cid)  # no prompt ID, pair or model name in it


def test_orientation_is_mixed():
    _, key = build(PROMPTS * 5, seed=4)
    flipped = sum(1 for info in key.values() if info["A"] == info["pair"].split("-")[1])
    assert 0 < flipped < len(key)


def test_tally_counts_wins_and_ties():
    _, key = build(PROMPTS[:1], seed=5)
    ratings = [{"comparison_id": cid, "choice": "A"} for cid in key]  # rater picks A, always
    result = tally(key, ratings)
    assert result["position_a_share"]["value"] == pytest.approx(1.0)
    decided = {p: v for p, v in result.items() if p != "position_a_share"}
    assert sum(v["first_wins"] + v["second_wins"] for v in decided.values()) == len(ratings)


def test_ties_are_not_wins():
    _, key = build(PROMPTS[:1], seed=6)
    cid = next(iter(key))
    result = tally(key, [{"comparison_id": cid, "choice": "tie"}])
    pair = key[cid]["pair"]
    assert result[pair]["ties"] == 1
    assert result[pair]["first_wins"] + result[pair]["second_wins"] == 0


def test_wilson_empty_and_bounds():
    assert wilson(0, 0) == (0.0, 0.0)
    low, high = wilson(50, 100)
    assert 0.39 < low < 0.41
    assert 0.59 < high < 0.61


def test_camera_reading_is_shown_to_the_rater():
    prompts = [{**PROMPTS[0], "camera": "ok: happy"}]
    visible, _ = build(prompts, seed=7)
    assert all(row["camera"] == "ok: happy" for row in visible)


def test_missing_camera_reading_says_not_given():
    visible, _ = build(PROMPTS[:1], seed=8)
    assert all(row["camera"] == "not given" for row in visible)
