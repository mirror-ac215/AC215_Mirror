"""Relabel FER-2013 with FER+ votes (M3-18 test baseline, M3-01 soft-label training).

FER+ (Microsoft, MIT licence) gives 10 annotator votes for every row of the original
fer2013.csv. Our FER-2013 v1 images come from the Kaggle folder copy: the file names carry
no row number and the pixels were JPEG-compressed. So each image is matched to its
fer2013.csv row by pixels, within the same split (Training/PublicTest/PrivateTest) and the
same original label. Writes the FER-2013 v1 layout for train, val and test, so cv-eval and
cv-train read it unchanged; each manifest row also carries its 7 vote counts (soft labels).
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
MIRROR_CLASSES = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]
VOTE_COLUMNS = [f"votes_{label}" for label in MIRROR_CLASSES]
# Our train and val both come from Kaggle's train folder (= fer2013.csv "Training").
SPLIT_USAGES = {"train": ("Training",), "val": ("Training",), "test": ("PublicTest", "PrivateTest")}


def majority(votes: Sequence[int]) -> str:
    """The FER+ column with the most votes, or 'tie' when two columns share the top count."""
    top = max(votes)
    winners = [name for name, count in zip(FERPLUS_VOTES, votes, strict=True) if count == top]
    return winners[0] if len(winners) == 1 else "tie"


def mirror_votes(votes: dict[str, int]) -> list[int]:
    """The vote counts for our 7 classes, in Mirror's class order."""
    by_mirror = {FERPLUS_TO_MIRROR[name]: votes[name] for name in FERPLUS_TO_MIRROR}
    return [by_mirror[label] for label in MIRROR_CLASSES]


def read_rows(fer2013_csv: Path, ferplus_csv: Path) -> list[dict]:
    """Every fer2013.csv row with its pixels, FER+ majority and Mirror vote counts."""
    csv.field_size_limit(10_000_000)  # one pixels field is ~9 KB
    with fer2013_csv.open(encoding="utf-8") as a, ferplus_csv.open(encoding="utf-8") as b:
        original, plus = csv.DictReader(a), csv.DictReader(b)
        rows = []
        for index, (row, votes) in enumerate(zip(original, plus, strict=True)):
            if row["Usage"] != votes["Usage"]:
                raise ValueError(f"row {index}: fer2013.csv and FER+ disagree on the split")
            counts = {name: int(votes[name]) for name in FERPLUS_VOTES}
            rows.append(
                {
                    "usage": row["Usage"],
                    "label": FER2013_LABELS[int(row["emotion"])],
                    "pixels": np.array(row["pixels"].split(), dtype=np.uint8),
                    "majority": majority([counts[name] for name in FERPLUS_VOTES]),
                    "votes": mirror_votes(counts),
                }
            )
    return rows


def rms_distances(ours: np.ndarray, theirs: np.ndarray) -> np.ndarray:
    """Root-mean-square pixel difference between every pair of images (grey levels)."""
    squared = (ours**2).sum(1)[:, None] + (theirs**2).sum(1)[None, :] - 2 * ours @ theirs.T
    return np.sqrt(np.maximum(squared, 0) / ours.shape[1])


def relabel_split(
    fer_dir: Path, split: str, candidates: list[dict], output_dir: Path, max_rms: float,
    outcome: Counter[str],
) -> list[dict[str, str]]:
    with (fer_dir / "manifests" / f"{split}.csv").open(encoding="utf-8") as handle:
        ours = list(csv.DictReader(handle))
    rows = []
    for usage in SPLIT_USAGES[split]:
        for label in FER2013_LABELS:
            mine = [r for r in ours if r["label"] == label and Path(r["path"]).name.startswith(usage)]
            theirs = [c for c in candidates if c["usage"] == usage and c["label"] == label]
            if not mine:
                continue
            pixels = np.stack(
                [np.asarray(Image.open(fer_dir / "images" / r["path"]).convert("L"), dtype=np.float32)
                 .reshape(-1) for r in mine]
            )
            reference = np.stack([c["pixels"] for c in theirs]).astype(np.float32)
            close = rms_distances(pixels, reference) <= max_rms
            for row, hits in zip(mine, close, strict=True):
                # Duplicate photos in FER-2013 can match several rows: fine if they agree.
                matches = [theirs[j] for j in np.flatnonzero(hits)]
                majorities = {match["majority"] for match in matches}
                if not majorities:
                    outcome[f"{split}: unmatched"] += 1
                elif len(majorities) > 1:
                    outcome[f"{split}: ambiguous duplicate"] += 1
                elif (new := FERPLUS_TO_MIRROR.get(majorities.pop())) is None:
                    outcome[f"{split}: no Mirror label (tie/contempt/unknown/NF)"] += 1
                else:
                    outcome[f"{split}: kept"] += 1
                    if new != row["label"]:
                        outcome[f"{split}: relabelled"] += 1
                    relative = Path(split) / new / Path(row["path"]).name
                    destination = output_dir / "images" / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(fer_dir / "images" / row["path"], destination)
                    rows.append({"path": relative.as_posix(), "label": new, "split": split,
                                 **dict(zip(VOTE_COLUMNS, map(str, matches[0]["votes"]), strict=True))})
    return sorted(rows, key=lambda r: (r["label"], r["path"]))


def prepare(
    fer_dir: Path, fer2013_csv: Path, ferplus_csv: Path, output_dir: Path, *, max_rms: float = 3.0
) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"{output_dir} already exists; delete it first to rebuild")
    candidates = read_rows(fer2013_csv, ferplus_csv)
    metadata = json.loads((fer_dir / "metadata" / "transform_spec.json").read_text())
    metadata["labels"] = (
        "FER+ majority vote (10 annotators); ties and non-Mirror classes dropped. "
        f"Columns {VOTE_COLUMNS[0]}..{VOTE_COLUMNS[-1]} hold the vote counts (soft labels)."
    )

    outcome: Counter[str] = Counter()
    balance = {}
    for split in SPLIT_USAGES:
        rows = relabel_split(fer_dir, split, candidates, output_dir, max_rms, outcome)
        manifest = output_dir / "manifests" / f"{split}.csv"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["path", "label", "split", *VOTE_COLUMNS])
            writer.writeheader()
            writer.writerows(rows)
        counts = Counter(r["label"] for r in rows)
        balance[split] = {label: counts[label] for label in metadata["class_order"]}

    report = {"outcome": dict(outcome), "class_balance": balance, "max_rms": max_rms}
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
    command.add_argument("--output", type=Path, default=Path("data/processed/ferplus/v2"))
    command.add_argument("--max-rms", type=float, default=3.0)
    args = command.parse_args(argv)
    report = prepare(
        args.fer_dir, args.fer2013_csv, args.ferplus_csv, args.output, max_rms=args.max_rms
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
