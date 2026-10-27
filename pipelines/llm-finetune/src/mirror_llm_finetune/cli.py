"""mirror-llm-finetune train | submit. See README for the full run order."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from mirror_llm_finetune.config import check, load_params
from mirror_llm_finetune.data import fingerprint

# Passed from your shell into the Vertex job; never written to params.yaml or git.
# GIT_SHA is not among them: it is baked into the image at build time (Dockerfile).
FORWARDED_ENV = ("WANDB_API_KEY", "HF_TOKEN")
REPO_ROOT = Path("../..")  # submit is run from pipelines/llm-finetune (README)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mirror-llm-finetune")
    p.add_argument("--params", type=Path, default=Path("params.yaml"))
    sub = p.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train", help="run QLoRA training (needs a GPU)")
    train.add_argument("--data-dir", type=Path, help="default: data.dir in params.yaml")
    train.add_argument("--out-dir", type=Path, default=Path("outputs"))
    train.add_argument("--upload", action="store_true", help="copy the adapter to GCS")
    submit = sub.add_parser("submit", help="run training as a Vertex AI custom job")
    submit.add_argument("--data-uri", required=True, help="gs:// folder with train/val/test.csv")
    submit.add_argument(
        "--local-data-dir",
        type=Path,
        help="DVC-pulled copy of the same data, to fingerprint (default: <repo root>/data.dir)",
    )
    submit.add_argument("--dry-run", action="store_true", help="print the job spec only")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    params = load_params(args.params)
    if args.command == "train":
        from mirror_llm_finetune.train import run

        data_dir = args.data_dir or Path(params["data"]["dir"])
        adapter = run(params, data_dir, args.out_dir, upload=args.upload)
        print(f"adapter saved to {adapter}")
        return 0

    from mirror_llm_finetune.vertex import job_spec, submit

    check(params, for_training=True)  # fail here, not after the GPU has started
    env = {k: os.environ[k] for k in FORWARDED_ENV if os.environ.get(k)}
    local = args.local_data_dir or REPO_ROOT / params["data"]["dir"]
    if not local.is_dir():
        raise FileNotFoundError(f"{local} not found: run `dvc pull` and `dvc repro persona_clean`")
    env["EXPECTED_DATA_SHA256"] = fingerprint(local)  # the job refuses any other data
    print(f"expected data sha256: {env['EXPECTED_DATA_SHA256']}", file=sys.stderr)
    spec = job_spec(params, args.data_uri, env)
    if args.dry_run:
        shown = json.loads(json.dumps(spec))
        for item in shown["worker_pool_specs"][0]["container_spec"]["env"]:
            item["value"] = "***"  # never print secrets
        print(json.dumps(shown, indent=2))
        return 0
    print(f"submitted {submit(params, spec)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
