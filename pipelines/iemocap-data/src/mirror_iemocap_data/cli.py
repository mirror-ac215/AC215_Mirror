from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the IEMOCAP evaluation table (M3-21).")
    parser.add_argument("--params", type=Path, required=True, help="params.yaml")
    parser.add_argument("--input", type=Path, help="Override input.source")
    parser.add_argument("--output", type=Path, help="Override output.local_dir")
    args = parser.parse_args()

    params = yaml.safe_load(args.params.read_text(encoding="utf-8"))
    source = args.input or Path(params["input"]["source"])
    out_dir = args.output or Path(params["output"]["local_dir"])
    report = run(source, out_dir, params)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
