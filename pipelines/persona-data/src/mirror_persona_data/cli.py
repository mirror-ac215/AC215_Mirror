from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean and split the persona pairs (M2-09).")
    parser.add_argument("--params", type=Path, required=True, help="params.yaml")
    parser.add_argument("--input", type=Path, help="Override input.raw_dir")
    parser.add_argument("--output", type=Path, help="Override output.local_dir")
    args = parser.parse_args()

    params = yaml.safe_load(args.params.read_text(encoding="utf-8"))
    raw_dir = args.input or Path(params["input"]["raw_dir"])
    out_dir = args.output or Path(params["output"]["local_dir"])
    report = run(raw_dir, out_dir, params)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
