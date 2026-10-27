"""Relabel the FER-2013 test images with FER+ majority votes (M3-18).

FER+ (Microsoft, MIT licence) gives 10 annotator votes for every row of the original
fer2013.csv. Our FER-2013 v1 images come from the Kaggle folder copy: the file names carry
no row number and the pixels were JPEG-compressed. So each test image is matched to its
fer2013.csv row by pixels, within the same split (PublicTest/PrivateTest) and the same
original label. Writes the FER-2013 v1 layout (test split only), so cv-eval reads it unchanged.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image

# fer2013.csv "emotion" codes 0-6.
FER2013_LABELS = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]
# fer2013new.csv vote columns, in file order. contempt / unknown / NF have no Mirror label.
FERPLUS_VOTES = [
    "neutral", "happiness", "surprise", "sadness", "anger",
    "disgust", "fear", "contempt", "unknown", "NF",
]
FERPLUS_TO_MIRROR = {
    "neutral": "neutral",
    "happiness": "happy",
    "surprise": "surprise",
    "sadness": "sad",
    "anger": "angry",
    "disgust": "disgust",
    "fear": "fear",
}


def majority(votes: Sequence[int]) -> str:
    """The FER+ column with the most votes, or 'tie' when two columns share the top count."""
    top = max(votes)
    winners = [name for name, count in zip(FERPLUS_VOTES, votes, strict=True) if count == top]
    return winners[0] if len(winners) == 1 else "tie"


def read_test_rows(fer2013_csv: Path, ferplus_csv: Path) -> list[dict]:
    """The test rows of fer2013.csv, each with its pixels and FER+ majority."""
    csv.field_size_limit(10_000_000)  # one pixels field is ~9 KB
    with fer2013_csv.open(encoding="utf-8") as a, ferplus_csv.open(encoding="utf-8") as b:
        original, plus = csv.DictReader(a), csv.DictReader(b)
        rows = []
        for index, (row, votes) in enumerate(zip(original, plus, strict=True)):
            if row["Usage"] != votes["Usage"]:
                raise ValueError(f"row {index}: fer2013.csv and FER+ disagree on the split")
            if row["Usage"] == "Training":
                continue
            rows.append(
                {
                    "usage": row["Usage"],
                    "label": FER2013_LABELS[int(row["emotion"])],
                    "pixels": np.array(row["pixels"].split(), dtype=np.float32),
                    "majority": majority([int(votes[name]) for name in FERPLUS_VOTES]),
                }
            )
    return rows


def rms_distances(ours: np.ndarray, theirs: np.ndarray) -> np.ndarray:
    """Root-mean-square pixel difference between every pair of images (grey levels)."""
    squared = (ours**2).sum(1)[:, None] + (theirs**2).sum(1)[None, :] - 2 * ours @ theirs.T
    return np.sqrt(np.maximum(squared, 0) / ours.shape[1])


def prepare(
    fer_dir: Path, fer2013_csv: Path, ferplus_csv: Path, output_dir: Path, *, max_rms: float = 3.0
) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"{output_dir} already exists; delete it first to rebuild")
    with (fer_dir / "manifests" / "test.csv").open(encoding="utf-8") as handle:
        ours = list(csv.DictReader(handle))
    candidates = read_test_rows(fer2013_csv, ferplus_csv)

    outcome: Counter[str] = Counter()
    rows = []
    for usage in ("PublicTest", "PrivateTest"):
        for label in FER2013_LABELS:
            mine = [r for r in ours if r["label"] == label and Path(r["path"]).name.startswith(usage)]
            theirs = [c for c in candidates if c["usage"] == usage and c["label"] == label]
            if not mine:
                continue
            pixels = np.stack(
                [np.asarray(Image.open(fer_dir / "images" / r["path"]).convert("L"), dtype=np.float32)
                 .reshape(-1) for r in mine]
            )
            close = rms_distances(pixels, np.stack([c["pixels"] for c in theirs])) <= max_rms
            for row, hits in zip(mine, close, strict=True):
                # Duplicate photos in FER-2013 can match several rows: fine if they agree.
                majorities = {theirs[j]["majority"] for j in np.flatnonzero(hits)}
                if not majorities:
                    outcome["unmatched"] += 1
                elif len(majorities) > 1:
                    outcome["ambiguous duplicate"] += 1
                elif (new := FERPLUS_TO_MIRROR.get(majorities.pop())) is None:
                    outcome["no Mirror label (tie/contempt/unknown/NF)"] += 1
                else:
                    outcome["kept"] += 1
                    outcome["relabelled"] += new != row["label"]
                    relative = Path("test") / new / Path(row["path"]).name
                    destination = output_dir / "images" / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(fer_dir / "images" / row["path"], destination)
                    rows.append({"path": relative.as_posix(), "label": new, "split": "test"})

    rows.sort(key=lambda r: (r["label"], r["path"]))
    manifest = output_dir / "manifests" / "test.csv"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "label", "split"])
        writer.writeheader()
        writer.writerows(rows)

    metadata = json.loads((fer_dir / "metadata" / "transform_spec.json").read_text())
    metadata["labels"] = "FER+ majority vote (10 annotators); ties and non-Mirror classes dropped"
    counts = Counter(r["label"] for r in rows)
    report = {
        "outcome": dict(outcome),
        "class_balance": {label: counts[label] for label in metadata["class_order"]},
        "max_rms": max_rms,
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
    command.add_argument("--fer-dir", type=Path, default=Path("data/processed/fer2013/v1"))
    command.add_argument("--fer2013-csv", type=Path, required=True)
    command.add_argument("--ferplus-csv", type=Path, required=True)
    command.add_argument("--output", type=Path, default=Path("data/processed/ferplus/v1"))
    command.add_argument("--max-rms", type=float, default=3.0)
    args = command.parse_args(argv)
    report = prepare(
        args.fer_dir, args.fer2013_csv, args.ferplus_csv, args.output, max_rms=args.max_rms
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
