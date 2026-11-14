"""Build blinded comparisons, and tally the ratings once the key is opened.

Input (jsonl, one prompt per line):
  {"prompt_id": "...", "prompt": "...", "camera": "ok: happy" | "uncertain" | "dropped" | "camera_off",
   "replies": {"base": "...", "lora": "...", "lora_visual": "..."}}
"camera" is the gate's reading for that moment, shown to the rater. Missing means "not given".

Output files:
  comparisons.jsonl  prompt, camera, reply_a, reply_b, comparison_id (what the rater sees)
  key.json           comparison_id -> prompt_id, pair, and which model is A and which is B (sealed)
comparison_id is opaque (c0001, c0002, ...), numbered after the shuffle: it carries no prompt,
pair or model name, and its order does not follow the pairs.
Ratings (ratings.jsonl): {"comparison_id": "...", "choice": "A" | "B" | "tie"}
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics
from collections import defaultdict

from mirror_pairwise import PAIRS

Z = 1.96


def wilson(successes: int, n: int) -> tuple[float, float]:
    """95% interval for a share; same formula as the fairness audit (M3-02)."""
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    centre = (p + Z * Z / (2 * n)) / (1 + Z * Z / n)
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def build(prompts: list[dict], seed: int) -> tuple[list[dict], dict]:
    """Every pair for every prompt, with a random A/B order; returns (visible, key)."""
    rng = random.Random(seed)
    rows = []
    for item in prompts:
        for left, right in PAIRS:
            flip = rng.random() < 0.5
            a, b = (right, left) if flip else (left, right)
            rows.append((item, a, b, f"{left}-{right}"))
    rng.shuffle(rows)  # the rater should not see the pairs in blocks
    visible, key = [], {}
    for n, (item, a, b, pair) in enumerate(rows, start=1):
        cid = f"c{n:04d}"  # opaque, like the style check's s0001: the pair stays in the key only
        visible.append(
            {
                "comparison_id": cid,
                "prompt": item["prompt"],
                "camera": item.get("camera", "not given"),
                "reply_a": item["replies"][a],
                "reply_b": item["replies"][b],
            }
        )
        key[cid] = {"prompt_id": item["prompt_id"], "A": a, "B": b, "pair": pair}
    return visible, key


def tally(key: dict, ratings: list[dict]) -> dict:
    """Win share per pair, with ties excluded from the share and counted separately."""
    wins = defaultdict(lambda: {"first": 0, "second": 0, "tie": 0})
    a_wins = 0
    decided = 0
    for r in ratings:
        info = key[r["comparison_id"]]
        if r["choice"] == "tie":
            wins[info["pair"]]["tie"] += 1
            continue
        winner = info[r["choice"]]
        decided += 1
        a_wins += r["choice"] == "A"
        first = winner == info["pair"].split("-")[0]
        wins[info["pair"]]["first" if first else "second"] += 1
    result = {}
    for pair, w in wins.items():
        n = w["first"] + w["second"]
        low, high = wilson(w["first"], n)
        result[pair] = {
            "first_wins": w["first"],
            "second_wins": w["second"],
            "ties": w["tie"],
            "share_first": w["first"] / n if n else 0.0,
            "low": low,
            "high": high,
        }
    # A rater who always picks A is a position bias, not a preference: report it.
    low, high = wilson(a_wins, decided)
    result["position_a_share"] = {
        "value": a_wins / decided if decided else 0.0,
        "low": low,
        "high": high,
    }
    return result


def write_blinded(prompts: list[dict], seed: int, out_dir: str) -> None:
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    visible, key = build(prompts, seed)
    with open(out / "comparisons.jsonl", "w") as f:
        f.writelines(json.dumps(row) + "\n" for row in visible)
    (out / "key.json").write_text(json.dumps(key, indent=2))


def sentence_count(text: str) -> int:
    """Rough sentence count: runs of . ! or ? followed by a space or the end of the text."""
    parts = [p for p in re.split(r"[.!?]+(?:\s+|$)", text.strip()) if p.strip()]
    return len(parts)


def length_report(rows: list[dict]) -> dict:
    """Median sentence count per model, reported apart from the rater's choice.

    rows: [{"model": "base", "reply": "..."}, ...]. The prompt asks for 2 to 4 sentences.
    """
    by_model = defaultdict(list)
    for row in rows:
        by_model[row["model"]].append(sentence_count(row["reply"]))
    return {
        model: {
            "median_sentences": statistics.median(counts),
            "n": len(counts),
            "under_2_share": sum(c < 2 for c in counts) / len(counts),
        }
        for model, counts in by_model.items()
        if counts
    }
