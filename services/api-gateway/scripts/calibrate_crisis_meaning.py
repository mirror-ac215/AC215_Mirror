"""Calibrate the M4-15 meaning layer: scores, a suggested threshold, and the model pin.

Needs the model (downloads it on first run). From services/api-gateway:

    uv run python scripts/calibrate_crisis_meaning.py

Prints every test sentence with its crisis and safe similarity, the gap between the
lowest must-fire score and the highest must-not-fire score, and the Hugging Face
commit to pin in app/config.py. It changes no file: copy the numbers into the config.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.config import Settings
from app.crisis_meaning import CrisisMeaning, load_hf_embedder

TESTS = Path(__file__).resolve().parents[1] / "tests"


def main() -> None:
    s = Settings()
    from huggingface_hub import model_info

    sha = model_info(s.crisis_meaning_model, revision=s.crisis_meaning_revision).sha
    embedder = load_hf_embedder(s.crisis_meaning_model, sha, 128, local_files_only=False)
    layer = CrisisMeaning(
        threshold=s.crisis_meaning_threshold, margin=s.crisis_meaning_margin, embedder=embedder
    )

    cases = yaml.safe_load((TESTS / "safety_meaning_cases.yaml").read_text())
    everyday = [
        c["text"]
        for c in yaml.safe_load((TESTS / "safety_cases.yaml").read_text())
        if c["expect"] == "none"
    ]
    fire = [(t, layer.score(t)) for t in cases["must_fire"]]
    quiet = [(t, layer.score(t)) for t in cases["must_not_fire"] + everyday]

    print(f"model {s.crisis_meaning_model} @ {sha}\n")
    print("MUST FIRE (crisis, safe, gap, closest example)")
    for t, sc in sorted(fire, key=lambda x: x[1].crisis):
        print(f"  {sc.crisis:.3f} {sc.safe:.3f} {sc.crisis - sc.safe:+.3f} {sc.crisis_id:<14} {t}")
    print("\nMUST NOT FIRE (highest crisis first)")
    for t, sc in sorted(quiet, key=lambda x: -x[1].crisis)[:15]:
        print(f"  {sc.crisis:.3f} {sc.safe:.3f} {sc.crisis - sc.safe:+.3f} {sc.crisis_id:<14} {t}")

    low_fire = min(sc.crisis for _, sc in fire)
    high_quiet = max(sc.crisis for _, sc in quiet)
    print(f"\nlowest must-fire crisis score:     {low_fire:.3f}")
    print(f"highest must-not-fire crisis score: {high_quiet:.3f}")
    if low_fire > high_quiet:
        print(f"separable: suggested threshold {(low_fire + high_quiet) / 2:.2f}")
    else:
        print("NOT separable by threshold alone: check the margin column, or add examples")
    misses = [t for t, _ in fire if layer.check(t) is None]
    alarms = [t for t, _ in quiet if layer.check(t) is not None]
    print(
        f"with current threshold {layer.threshold} / margin {layer.margin}: "
        f"{len(misses)} misses, {len(alarms)} false alarms"
    )
    print(f'\npin in app/config.py: crisis_meaning_revision: str = "{sha}"')


if __name__ == "__main__":
    main()
