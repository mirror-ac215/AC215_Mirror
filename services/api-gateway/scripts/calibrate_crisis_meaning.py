"""Calibrate the M4-15 meaning layer: choose threshold and margin on dev, judge on holdout.

Needs the model (downloads it on first run). From services/api-gateway:

    uv run python -m scripts.calibrate_crisis_meaning

1. Scores every sentence in tests/safety_meaning_cases.yaml (dev and holdout) and
   every `expect: none` case in tests/safety_cases.yaml (added to dev must-not-fire).
2. Chooses the threshold and margin on dev only: fewest misses first, then fewest
   false alarms, then the highest threshold.
3. Applies them, unchanged, to holdout. That is the honest result.
4. Prints the Hugging Face commit to pin. It changes no file.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.config import Settings
from app.crisis_meaning import CrisisMeaning, MeaningScore, load_hf_embedder

TESTS = Path(__file__).resolve().parents[1] / "tests"
FIELDS = Settings.model_fields  # read defaults without needing DATABASE_URL etc.


def fires(s: MeaningScore, threshold: float, margin: float) -> bool:
    return s.crisis >= threshold and s.crisis - s.safe >= margin


def count(fire, quiet, threshold, margin) -> tuple[int, int]:
    misses = sum(not fires(s, threshold, margin) for _, s in fire)
    alarms = sum(fires(s, threshold, margin) for _, s in quiet)
    return misses, alarms


def show(title: str, rows, threshold: float, margin: float) -> None:
    print(title)
    for text, s in sorted(rows, key=lambda r: -r[1].crisis):
        mark = "FIRES" if fires(s, threshold, margin) else "quiet"
        gap = s.crisis - s.safe
        print(f"  {mark} {s.crisis:.3f} {s.safe:.3f} {gap:+.3f} {s.crisis_id:<14} {text}")


def main() -> None:
    from huggingface_hub import model_info

    model = FIELDS["crisis_meaning_model"].default
    sha = model_info(model, revision=FIELDS["crisis_meaning_revision"].default).sha
    layer = CrisisMeaning(
        threshold=0.0,
        margin=0.0,
        embedder=load_hf_embedder(model, sha, 128, local_files_only=False),
    )
    cases = yaml.safe_load((TESTS / "safety_meaning_cases.yaml").read_text())
    everyday = [
        c["text"]
        for c in yaml.safe_load((TESTS / "safety_cases.yaml").read_text())
        if c["expect"] == "none"
    ]

    def scored(texts):
        return [(t, layer.score(t)) for t in texts]

    dev_fire = scored(cases["dev"]["must_fire"])
    dev_quiet = scored(cases["dev"]["must_not_fire"] + everyday)
    hold_fire = scored(cases["holdout"]["must_fire"])
    hold_quiet = scored(cases["holdout"]["must_not_fire"])

    grid = [
        (t / 100, m / 100) for t in range(20, 91) for m in range(0, 41)
    ]  # thresholds 0.20-0.90, margins 0.00-0.40
    best = min(
        grid,
        key=lambda tm: (*count(dev_fire, dev_quiet, *tm), -tm[0]),
    )
    threshold, margin = best

    print(f"model {model} @ {sha}")
    print(f"chosen on dev: threshold {threshold:.2f}, margin {margin:.2f}\n")
    show("DEV MUST FIRE", dev_fire, threshold, margin)
    show(
        "DEV MUST NOT FIRE (top 12)",
        sorted(dev_quiet, key=lambda r: -r[1].crisis)[:12],
        threshold,
        margin,
    )
    show("\nHOLDOUT MUST FIRE", hold_fire, threshold, margin)
    show("HOLDOUT MUST NOT FIRE", hold_quiet, threshold, margin)

    dm, da = count(dev_fire, dev_quiet, threshold, margin)
    hm, ha = count(hold_fire, hold_quiet, threshold, margin)
    print(f"\ndev:     {dm} of {len(dev_fire)} missed, {da} of {len(dev_quiet)} false alarms")
    print(f"holdout: {hm} of {len(hold_fire)} missed, {ha} of {len(hold_quiet)} false alarms")
    print("\nfor app/config.py:")
    print(f'  crisis_meaning_revision: str = "{sha}"')
    print(f"  crisis_meaning_threshold = {threshold:.2f}, crisis_meaning_margin = {margin:.2f}")


if __name__ == "__main__":
    main()
