from __future__ import annotations

import csv
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from PIL import Image

from mirror_data_preprocess.pipeline import preprocess_dataset


CLASS_ORDER = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]


def _make_source_archive(path: Path) -> None:
    image_dir = path.parent / "images"
    image_dir.mkdir()
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for split, per_class in (("train", 5), ("test", 2)):
            for label_index, label in enumerate(CLASS_ORDER):
                for index in range(per_class):
                    image_path = image_dir / f"{split}-{label}-{index}.png"
                    Image.new("L", (48, 48), color=label_index * 20 + index).save(image_path)
                    archive.write(image_path, f"{split}/{label}/{index}.png")
        archive.writestr("train/angry/corrupt.png", b"not a PNG")


def _params() -> dict[str, object]:
    return {
        "dataset": {"class_order": CLASS_ORDER},
        "split": {"train_fraction": 0.8, "validation_fraction": 0.2, "seed": 42},
        "image": {"stored_format": "png", "stored_width": 48, "stored_height": 48},
        "inference_transform": {
            "grayscale_to_channels": 3,
            "resize": [224, 224],
            "pixel_range": [0.0, 1.0],
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
        },
    }


def _manifest_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_preprocess_validates_images_creates_disjoint_deterministic_splits_and_metadata(
    tmp_path: Path,
) -> None:
    source = tmp_path / "fer2013.zip"
    _make_source_archive(source)
    output_one = tmp_path / "out-one"
    output_two = tmp_path / "out-two"

    preprocess_dataset(source, output_one, _params())
    preprocess_dataset(source, output_two, _params())

    train = _manifest_rows(output_one / "manifests" / "train.csv")
    validation = _manifest_rows(output_one / "manifests" / "val.csv")
    test = _manifest_rows(output_one / "manifests" / "test.csv")
    assert len(train) == 28
    assert len(validation) == 7
    assert len(test) == 14
    assert {row["label"] for row in train + validation + test} == set(CLASS_ORDER)
    assert not ({row["path"] for row in train} & {row["path"] for row in validation})
    assert not ({row["path"] for row in train} & {row["path"] for row in test})
    assert not ({row["path"] for row in validation} & {row["path"] for row in test})
    assert (output_one / "images" / train[0]["path"]).exists()

    report = json.loads((output_one / "reports" / "data_report.json").read_text())
    assert report["source_counts"]["total_files"] == 50
    assert report["validation"]["corrupt_files"] == 1
    assert report["split_counts"] == {"test": 14, "train": 28, "val": 7}

    metadata = json.loads((output_one / "metadata" / "transform_spec.json").read_text())
    assert metadata["inference_transform"]["resize"] == [224, 224]
    assert metadata["inference_transform"]["grayscale_to_channels"] == 3
    assert metadata["training_augmentations_excluded"]

    for name in ("train.csv", "val.csv", "test.csv"):
        assert (output_one / "manifests" / name).read_bytes() == (
            output_two / "manifests" / name
        ).read_bytes()


def test_preprocess_preserves_existing_output_when_validation_fails(tmp_path: Path) -> None:
    invalid_source = tmp_path / "invalid.zip"
    with ZipFile(invalid_source, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("train/angry/not-an-image.png", b"not a PNG")
    output = tmp_path / "existing-output"
    output.mkdir()
    sentinel = output / "previously-valid.txt"
    sentinel.write_text("preserve me", encoding="utf-8")

    with pytest.raises(ValueError, match="every expected class"):
        preprocess_dataset(invalid_source, output, _params())

    assert sentinel.read_text(encoding="utf-8") == "preserve me"
