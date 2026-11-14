"""Style distinctness (Patrick, Oct 16): can blind raters tell a LoRA reply from a base-model reply?

Each reply is shown alone. The rater guesses its source: "base" or "lora".
Both LoRA variants count as "lora". Chance is 50%. If the interval's lower bound is above 0.5,
raters can tell the two apart; if the interval contains 0.5, they cannot.
"""

from __future__ import annotations

import random

from mirror_pairwise.pairwise import wilson

SOURCE = {"base": "base", "lora": "lora", "lora_visual": "lora"}


def build_items(replies: list[dict], seed: int) -> tuple[list[dict], dict]:
    """replies: [{"item_id": "...", "model": "base" | "lora" | "lora_visual", "reply": "..."}].
    Returns (visible items with no model name, sealed key)."""
    rng = random.Random(seed)
    order = list(range(len(replies)))
    rng.shuffle(order)
    visible, key = [], {}
    for n, i in enumerate(order):
        row = replies[i]
        item_id = f"s{n:04d}"
        visible.append({"item_id": item_id, "reply": row["reply"]})
        key[item_id] = SOURCE[row["model"]]
    return visible, key


def score(key: dict, guesses: list[dict]) -> dict:
    """Accuracy of guesses against the sealed key, with a Wilson 95% interval."""
    correct = sum(1 for g in guesses if key[g["item_id"]] == g["guess"])
    n = len(guesses)
    low, high = wilson(correct, n)
    return {
        "n": n,
        "accuracy": correct / n if n else 0.0,
        "low": low,
        "high": high,
        "verdict": (
            "raters can tell them apart"
            if low > 0.5
            else "no clear difference from chance"
            if high >= 0.5
            else "raters are below chance"
        ),
    }
