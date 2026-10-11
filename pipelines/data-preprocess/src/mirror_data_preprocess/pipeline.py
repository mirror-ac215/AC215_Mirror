from __future__ import annotations

import csv
import io
import json
import random
import shutil
from uuid import uuid4
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from PIL import Image, UnidentifiedImageError


@dataclass(frozen=True)
class Sample:
    source_split: str
    label: str
    filename: str
    image_bytes: bytes


def _required_class_order(params: dict[str, Any]) -> list[str]:
    values = params["dataset"]["class_order"]
    if not isinstance(values, list) or not values:
        raise ValueError("dataset.class_order must be a non-empty list")
    return [str(value) for value in values]


def _read_valid_samples(source_archive: Path, params: dict[str, Any]) -> tuple[list[Sample], dict[str, Any]]:
    labels = set(_required_class_order(params))
    expected_size = (int(params["image"]["stored_width"]), int(params["image"]["stored_height"]))
    samples: list[Sample] = []
    corrupt_files = 0
    malformed_paths = 0
    source_counts: Counter[str] = Counter()

    with ZipFile(source_archive) as archive:
        for name in sorted(entry for entry in archive.namelist() if not entry.endswith("/")):
            source_counts["total_files"] += 1
            parts = name.split("/")
            if len(parts) != 3 or parts[0] not in {"train", "test"} or parts[1] not in labels:
                malformed_paths += 1
                continue
            try:
                image_bytes = archive.read(name)
                with Image.open(io.BytesIO(image_bytes)) as image:
                    image.verify()
                with Image.open(io.BytesIO(image_bytes)) as image:
                    if image.size != expected_size:
                        raise ValueError(f"expected {expected_size}, got {image.size}")
            except (UnidentifiedImageError, OSError, ValueError):
                corrupt_files += 1
                continue
            samples.append(Sample(parts[0], parts[1], parts[2], image_bytes))

    report = {
        "source_counts": dict(source_counts),
        "validation": {
            "valid_files": len(samples),
            "corrupt_files": corrupt_files,
            "malformed_paths": malformed_paths,
        },
    }
    return samples, report


def _split_train_validation(samples: list[Sample], params: dict[str, Any]) -> tuple[list[Sample], list[Sample]]:
    seed = int(params["split"]["seed"])
    train_fraction = float(params["split"]["train_fraction"])
    validation_fraction = float(params["split"]["validation_fraction"])
    if round(train_fraction + validation_fraction, 8) != 1.0:
        raise ValueError("train_fraction and validation_fraction must sum to 1")

    grouped: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        grouped[sample.label].append(sample)

    train: list[Sample] = []
    validation: list[Sample] = []
    for label in sorted(grouped):
        ordered = sorted(grouped[label], key=lambda sample: sample.filename)
        random.Random(f"{seed}:{label}").shuffle(ordered)
        train_count = int(len(ordered) * train_fraction)
        if len(ordered) > 1:
            train_count = max(1, min(len(ordered) - 1, train_count))
        train.extend(ordered[:train_count])
        validation.extend(ordered[train_count:])
    return train, validation


def _write_samples(output_dir: Path, split: str, samples: list[Sample]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for sample in sorted(samples, key=lambda item: (item.label, item.filename)):
        relative_path = Path(split) / sample.label / sample.filename
        destination = output_dir / "images" / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(io.BytesIO(sample.image_bytes)) as image:
            image.convert("L").save(destination, format="PNG")
        rows.append({"path": relative_path.as_posix(), "label": sample.label, "split": split})
    return rows


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "label", "split"])
        writer.writeheader()
        writer.writerows(rows)


def _class_balance(rows: list[dict[str, str]], classes: list[str]) -> dict[str, int]:
    counts = Counter(row["label"] for row in rows)
    return {label: counts[label] for label in classes}


def preprocess_dataset(source_archive: Path, output_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic, validated FER-2013 v1 dataset from the raw archive."""
    source_archive = Path(source_archive)
    output_dir = Path(output_dir)
    if not source_archive.is_file():
        raise FileNotFoundError(source_archive)

    classes = _required_class_order(params)
    samples, report = _read_valid_samples(source_archive, params)
    training_source = [sample for sample in samples if sample.source_split == "train"]
    test_source = [sample for sample in samples if sample.source_split == "test"]
    train_source_labels = {sample.label for sample in training_source}
    test_source_labels = {sample.label for sample in test_source}
    if train_source_labels != set(classes) or test_source_labels != set(classes):
        raise ValueError("every expected class must be present in both source splits")

    work_dir = output_dir.parent / f".{output_dir.name}.tmp-{uuid4().hex}"
    backup_dir = output_dir.parent / f".{output_dir.name}.backup-{uuid4().hex}"
    try:
        train_source, validation_source = _split_train_validation(training_source, params)
        train_rows = _write_samples(work_dir, "train", train_source)
        validation_rows = _write_samples(work_dir, "val", validation_source)
        test_rows = _write_samples(work_dir, "test", test_source)
        _write_manifest(work_dir / "manifests" / "train.csv", train_rows)
        _write_manifest(work_dir / "manifests" / "val.csv", validation_rows)
        _write_manifest(work_dir / "manifests" / "test.csv", test_rows)

        report["class_balance"] = {
            "train": _class_balance(train_rows, classes),
            "val": _class_balance(validation_rows, classes),
            "test": _class_balance(test_rows, classes),
        }
        report["split_counts"] = {
            "train": len(train_rows),
            "val": len(validation_rows),
            "test": len(test_rows),
        }
        report["source_archive"] = source_archive.as_posix()
        report_path = work_dir / "reports" / "data_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        metadata = {
            "class_order": classes,
            "inference_transform": params["inference_transform"],
            "stored_image": params["image"],
            "training_augmentations_excluded": [
                "RandomHorizontalFlip",
                "ColorJitter",
                "RandomErasing",
                "Mixup",
                "CutMix",
            ],
            "checkpoint": "gs://mirror-ac215-data/models/cv/inherited-v3/vit_b16_v3_best.pth",
            "split": params["split"],
        }
        metadata_path = work_dir / "metadata" / "transform_spec.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        if output_dir.exists():
            output_dir.replace(backup_dir)
        try:
            work_dir.replace(output_dir)
        except Exception:
            if backup_dir.exists():
                backup_dir.replace(output_dir)
            raise
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    return report
