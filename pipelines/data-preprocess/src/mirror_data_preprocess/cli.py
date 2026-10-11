from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml
from google.cloud import storage

from .pipeline import preprocess_dataset
from .publish import publish_directory


def _load_params(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError("params.yaml must contain a mapping")
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the versioned FER-2013 dataset.")
    parser.add_argument("--input", type=Path, help="Override params dataset.raw_archive")
    parser.add_argument("--output", type=Path, help="Override params output.local_dir")
    parser.add_argument("--params", type=Path, required=True, help="Pipeline parameters YAML")
    parser.add_argument("--publish", action="store_true", help="Upload validated outputs to GCS")
    args = parser.parse_args()

    params = _load_params(args.params)
    input_path = args.input or Path(str(params["dataset"]["raw_archive"]))
    output_path = args.output or Path(str(params["output"]["local_dir"]))
    report = preprocess_dataset(input_path, output_path, params)
    if args.publish:
        workers = int(params["output"]["publish_workers"])
        uploaded = publish_directory(
            output_path, str(params["output"]["gcs_uri"]), storage.Client(), max_workers=workers
        )
        print(f"Published {uploaded} files to {params['output']['gcs_uri']}")
    print(f"Processed split counts: {report['split_counts']}")


if __name__ == "__main__":
    main()
