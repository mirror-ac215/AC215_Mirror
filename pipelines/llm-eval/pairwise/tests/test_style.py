import pytest

from mirror_pairwise.style import build_items, score


def replies(n):
    models = ["base", "lora", "lora_visual"]
    return [{"item_id": f"x{i}", "model": models[i % 3], "reply": f"reply {i}"} for i in range(n)]


def test_visible_items_hide_the_model():
    visible, _ = build_items(replies(9), seed=1)
    for item in visible:
        assert set(item) == {"item_id", "reply"}


def test_key_matches_replies_and_merges_lora_variants():
    rows = replies(9)
    visible, key = build_items(rows, seed=2)
    by_text = {r["reply"]: r["model"] for r in rows}
    for item in visible:
        expected = {"base": "base", "lora": "lora", "lora_visual": "lora"}[by_text[item["reply"]]]
        assert key[item["item_id"]] == expected


def test_perfect_guesses_show_a_difference():
    visible, key = build_items(replies(60), seed=3)
    guesses = [{"item_id": v["item_id"], "guess": key[v["item_id"]]} for v in visible]
    result = score(key, guesses)
    assert result["accuracy"] == pytest.approx(1.0)
    assert result["verdict"] == "raters can tell them apart"


def test_coin_flip_guesses_show_no_difference():
    visible, key = build_items(replies(200), seed=4)
    guesses = [{"item_id": v["item_id"], "guess": "base" if i % 2 else "lora"}
               for i, v in enumerate(visible)]
    result = score(key, guesses)
    assert result["low"] < 0.5 < result["high"]
    assert result["verdict"] == "no clear difference from chance"
