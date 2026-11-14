"""Pick the held-out prompts: from the persona test split only, never a prompt seen in training.

The sample is fixed by the seed, so the same prompts come back on every run.
"""

from __future__ import annotations

import random


def held_out(test_rows: list[dict], train_prompts: set[str], n: int, seed: int) -> list[dict]:
    """n prompts from the test split whose question was not in the training data."""
    seen = {p.strip().lower() for p in train_prompts}
    candidates = [r for r in test_rows if r["prompt"].strip().lower() not in seen]
    if len(candidates) < n:
        raise ValueError(f"only {len(candidates)} unseen test prompts, need {n}")
    candidates.sort(key=lambda r: r["prompt_id"])  # a fixed order before sampling
    return random.Random(seed).sample(candidates, n)
