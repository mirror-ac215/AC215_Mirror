"""Export the CV model's per-frame probabilities on Aff-Wild2 videos (M3-04 threshold sweep, step 1).

One row per labelled frame: video, time in seconds (frame number / fps), true label and the 7
probabilities, from the same grey 224x224 input cv-service uses. The sweep
(services/api-gateway/scripts/gate_sweep.py) replays these rows through the real gate, so the
GPU work happens only once. Use the validation split: thresholds are chosen on it, never on test.

Run from the repository root:
    uv run --no-sync --project pipelines/cv-eval python pipelines/cv-eval/scripts/export_frame_probs.py \\
        --checkpoint data/models/m3-01-C3.pth --output data/reports/v4_affwild2_val_frames.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import torch
from PIL import Image

from mirror_cv_eval.cli import load_model, transform_from_metadata


def main() -> int:
    command = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    command.add_argument("--data-dir", type=Path, default=Path("data/processed/affwild2/v1"))
    command.add_argument("--split", default="val")
    command.add_argument("--checkpoint", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--fps", type=float, default=30.0, help="Aff-Wild2 videos are recorded at about 30 fps")
    command.add_argument("--batch-size", type=int, default=64)
    args = command.parse_args()

    metadata = json.loads((args.data_dir / "metadata" / "transform_spec.json").read_text())
    labels = list(metadata["class_order"])
    transform = transform_from_metadata(metadata["inference_transform"])
    with (args.data_dir / "manifests" / f"{args.split}.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_model(args.checkpoint).to(device)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle, torch.inference_mode():
        writer = csv.writer(handle)
        writer.writerow(["video", "t", "label", *labels])
        for start in range(0, len(rows), args.batch_size):
            batch = rows[start:start + args.batch_size]
            images = [Image.open(args.data_dir / "images" / row["path"]).convert("L").convert("RGB") for row in batch]
            probabilities = torch.softmax(model(torch.stack([transform(i) for i in images]).to(device)), dim=1)
            for row, values in zip(batch, probabilities.cpu().tolist(), strict=True):
                video, frame = Path(row["path"]).stem.rsplit("_", 1)  # <video>_<frame number>.jpg
                writer.writerow([video, f"{int(frame) / args.fps:.3f}", row["label"], *(f"{v:.5f}" for v in values)])
    print(f"wrote {len(rows)} frames to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
