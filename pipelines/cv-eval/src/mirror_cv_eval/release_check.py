"""The FER+ release check (D-005, M4-14): run it before any CV model is published or handed to serving.

Same evaluator as mirror-cv-eval with nothing left to choose: FER+ test (ferplus/v2), macro-F1 >= 0.609,
no --report-only. CI has no FER-2013 images or GPU, so it runs by hand on a machine with the data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from mirror_cv_eval import cli

THRESHOLD = 0.609  # v3 scored 0.6089 and fails: a new model must beat the one it replaces
DATASET_VERSION = "ferplus/v2"
# The test manifest mirror-prepare-ferplus builds for ferplus/v2 (6,722 photos).
TEST_MANIFEST_SHA256 = "e78ccb955f8d3b0abaa9afcf6ffeb2354498bd798049a1f7e3dff25d1460fa7b"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="FER+ release check (D-005): fails below macro-F1 0.609")
    command.add_argument("--data-dir", type=Path, default=Path("data/processed/ferplus/v2"))
    command.add_argument("--checkpoint", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--code-revision", required=True)
    command.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    command.add_argument("--model-version", help="Default: the name stored in the checkpoint")
    command.add_argument("--model-uri", help="Where the checkpoint is published")
    command.add_argument("--wandb-project", help="Optionally log the aggregate result to W&B")
    return command


def run(args: argparse.Namespace) -> int:
    manifest = args.data_dir / "manifests" / "test.csv"
    if sha256_of(manifest) != TEST_MANIFEST_SHA256:
        raise SystemExit(f"{manifest}: not the ferplus/v2 test manifest; rebuild it with mirror-prepare-ferplus")
    eval_argv = [
        "--data-dir", str(args.data_dir), "--checkpoint", str(args.checkpoint), "--output", str(args.output),
        "--code-revision", args.code_revision, "--dataset-version", DATASET_VERSION,
        "--threshold", str(THRESHOLD), "--device", args.device,
    ]
    for flag, value in (("--model-version", args.model_version), ("--model-uri", args.model_uri), ("--wandb-project", args.wandb_project)):
        if value:
            eval_argv += [flag, value]
    status = cli.run(cli.parser().parse_args(eval_argv))
    report = json.loads(args.output.read_text())
    report["release_check"] = {"decision": "D-005", "checkpoint_sha256": sha256_of(args.checkpoint), "passed": status == 0}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    verdict = "PASS" if status == 0 else "FAIL"
    print(f"{verdict}: {report['identity']['model_version']} macro-F1 {report['metrics']['macro_f1']:.4f} on {DATASET_VERSION} (needs >= {THRESHOLD})")
    return status


def main(argv: Sequence[str] | None = None) -> int:
    return run(parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
