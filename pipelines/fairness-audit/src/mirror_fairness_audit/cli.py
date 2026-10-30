"""mirror-fairness-audit score | report. See README for the run order."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mirror-fairness-audit")
    p.add_argument("--params", type=Path, default=Path("params.yaml"))
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("score", help="run the CV model on every FairFace photo (slow; GPU helps)")
    s.add_argument("--images-dir", type=Path, required=True, help="folder that holds val/*.jpg")
    s.add_argument("--labels", type=Path, required=True, help="fairface_label_val.csv")
    s.add_argument("--checkpoint", type=Path, required=True, help="local copy of model.uri")
    s.add_argument("--output", type=Path, required=True, help="predictions.csv (keep out of git)")
    s.add_argument("--device", default="cpu")
    s.add_argument("--limit", type=int, help="score only the first N photos (smoke test)")
    s.add_argument("--code-revision", default="unknown", help="git rev-parse HEAD")

    r = sub.add_parser("report", help="per-group numbers and the largest gap (fast, CPU)")
    r.add_argument("--predictions", type=Path, required=True)
    r.add_argument("--output-dir", type=Path, required=True)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    params = yaml.safe_load(args.params.read_text())

    if args.command == "score":
        from mirror_fairness_audit import score
        from mirror_fairness_audit.fairface import read_labels

        photos = read_labels(args.labels)[: args.limit]
        model = score.load_model(args.checkpoint, args.device)
        rows = score.score(photos, args.images_dir, model, score.FaceDetector(), device=args.device)
        meta = {
            "model_version": params["model"]["version"],
            "checkpoint_sha256": score.sha256(args.checkpoint),
            "data_version": params["data"]["version"],
            "labels_sha256": score.sha256(args.labels),
            "code_revision": args.code_revision,
            "limit": args.limit,
        }
        count = score.write(rows, args.output, meta)
        print(f"scored {count} photos -> {args.output}")
        return 0

    from mirror_fairness_audit import report
    from mirror_fairness_audit.audit import audit, read_predictions

    meta_path = args.predictions.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    if meta.get("model_version", params["model"]["version"]) != params["model"]["version"]:
        raise ValueError(
            f"predictions come from {meta['model_version']}, params.yaml names "
            f"{params['model']['version']}: score again or fix model.version"
        )
    result = audit(read_predictions(args.predictions), params)
    report.write(result, params, meta, args.output_dir)
    print(report.headline(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
