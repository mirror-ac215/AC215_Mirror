"""Prepare Aff-Wild2 expression frames for Mirror (M3-18 baseline, M3-01 retrain).

Reads the licensed archives where they are (frames never go into Git or the cloud)
and writes the same layout as FER-2013 v1, so cv-eval and cv-train read it unchanged:
images/<split>/<label>/<video>_<frame>.jpg, manifests/<split>.csv, metadata/transform_spec.json.

Splits are by video, never by frame, so one person never appears on both sides:
- test: the official validation videos, held out (M3-18 baseline, M3-01 final score)
- train / val: the official training videos, split by video (val picks M3-01's checkpoint)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import zipfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

CLASS_ORDER = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]
# Aff-Wild2 expression codes. 7 ("other") and -1 (not annotated) have no Mirror label: dropped.
AFFWILD2_TO_MIRROR = {
    0: "neutral",
    1: "angry",
    2: "disgust",
    3: "fear",
    4: "happy",
    5: "sad",
    6: "surprise",
}
# Same load-time transform as FER-2013 v1 (pipelines/data-preprocess/params.yaml).
INFERENCE_TRANSFORM = {
    "grayscale_to_channels": 3,
    "resize": [224, 224],
    "pixel_range": [0.0, 1.0],
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225],
}
CHECKPOINT = "gs://mirror-ac215-data/models/cv/inherited-v3/vit_b16_v3_best.pth"


def read_labels(annotation_zip: Path) -> dict[str, str]:
    """Map 'video/frame.jpg' to a Mirror label, keeping only the 7 shared expressions."""
    with zipfile.ZipFile(annotation_zip) as archive:
        text = archive.read(archive.namelist()[0]).decode("utf-8")
    rows = csv.reader(io.StringIO(text))
    next(rows)  # header: image,valence,arousal,expression,aus...
    labels: dict[str, str] = {}
    for row in rows:
        label = AFFWILD2_TO_MIRROR.get(int(row[3]))
        if label:
            labels[row[0]] = label
    return labels


def video_of(frame_name: str) -> str:
    return frame_name.split("/")[0]


def split_videos(videos: set[str], val_fraction: float, seed: int) -> tuple[set[str], set[str]]:
    """Shuffle whole videos (sorted first, so the result is the same on every machine)."""
    ordered = sorted(videos)
    random.Random(seed).shuffle(ordered)
    n_val = max(1, round(len(ordered) * val_fraction))
    return set(ordered[n_val:]), set(ordered[:n_val])


def write_split(
    frames: zipfile.ZipFile, output_dir: Path, split: str, labels: dict[str, str]
) -> list[dict[str, str]]:
    """Copy each frame's original JPEG bytes (no re-encoding) and return its manifest rows."""
    rows = []
    for name in sorted(labels, key=lambda n: (labels[n], n)):  # same order as FER-2013 v1
        video, frame = name.split("/")
        relative = Path(split) / labels[name] / f"{video}_{frame}"
        destination = output_dir / "images" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(frames.read(name))
        rows.append({"path": relative.as_posix(), "label": labels[name], "split": split})
    return rows


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "label", "split"])
        writer.writeheader()
        writer.writerows(rows)


def prepare(
    frames_zip: Path,
    train_annotations: Path,
    val_annotations: Path,
    output_dir: Path,
    *,
    val_fraction: float = 0.15,
    seed: int = 42,
) -> dict[str, dict]:
    if output_dir.exists():
        raise FileExistsError(f"{output_dir} already exists; delete it first to rebuild")
    official_train = read_labels(train_annotations)
    official_val = read_labels(val_annotations)
    shared = {video_of(n) for n in official_train} & {video_of(n) for n in official_val}
    if shared:
        raise ValueError(f"videos in both official splits: {sorted(shared)[:5]}")

    train_videos, val_videos = split_videos(
        {video_of(n) for n in official_train}, val_fraction, seed
    )
    splits = {
        "train": {n: lab for n, lab in official_train.items() if video_of(n) in train_videos},
        "val": {n: lab for n, lab in official_train.items() if video_of(n) in val_videos},
        "test": official_val,
    }

    report: dict[str, dict] = {}
    with zipfile.ZipFile(frames_zip) as frames:
        for split, labels in splits.items():
            rows = write_split(frames, output_dir, split, labels)
            write_manifest(output_dir / "manifests" / f"{split}.csv", rows)
            counts = Counter(row["label"] for row in rows)
            report[split] = {
                "frames": len(rows),
                "videos": len({video_of(n) for n in labels}),
                "class_balance": {label: counts[label] for label in CLASS_ORDER},
            }

    metadata = {
        "class_order": CLASS_ORDER,
        "inference_transform": INFERENCE_TRANSFORM,
        "checkpoint": CHECKPOINT,
        "source": "Aff-Wild2 cropped_aligned frames (licensed, local only)",
        "split": {"by": "video", "val_fraction": val_fraction, "seed": seed},
    }
    for path, content in (
        (output_dir / "metadata" / "transform_spec.json", metadata),
        (output_dir / "reports" / "data_report.json", report),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    command = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    command.add_argument("--frames-zip", type=Path, required=True)
    command.add_argument("--train-annotations", type=Path, required=True)
    command.add_argument("--val-annotations", type=Path, required=True)
    command.add_argument("--output", type=Path, default=Path("data/processed/affwild2/v1"))
    command.add_argument("--val-fraction", type=float, default=0.15)
    command.add_argument("--seed", type=int, default=42)
    args = command.parse_args(argv)
    report = prepare(
        args.frames_zip,
        args.train_annotations,
        args.val_annotations,
        args.output,
        val_fraction=args.val_fraction,
        seed=args.seed,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
