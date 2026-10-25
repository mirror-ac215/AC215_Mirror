from __future__ import annotations

import csv
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from mirror_data_preprocess.affwild2 import prepare

HEADER = "image,valence,arousal,expression,aus\n"


def _annotations(path: Path, rows: list[tuple[str, int]]) -> Path:
    with ZipFile(path, "w") as archive:
        lines = "".join(f"{image},0.0,0.0,{code},0,0\n" for image, code in rows)
        archive.writestr(path.stem, HEADER + lines)
    return path


def _sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    # 4 training videos (2 frames each, one "other" frame dropped) and 1 validation video.
    train = [(f"t{v}/0000{f}.jpg", code) for v in range(4) for f, code in ((1, 4), (2, 7))]
    val = [("v0/00001.jpg", 5), ("v0/00002.jpg", -1), ("v0/00003.jpg", 0)]
    frames = tmp_path / "cropped_aligned.zip"
    with ZipFile(frames, "w") as archive:
        for image, _ in train + val:
            archive.writestr(image, b"jpeg-bytes-" + image.encode())
    return (
        frames,
        _annotations(tmp_path / "training_set_annotations.txt.zip", train),
        _annotations(tmp_path / "validation_set_annotations.txt.zip", val),
    )


def _manifest(output: Path, split: str) -> list[dict[str, str]]:
    with (output / "manifests" / f"{split}.csv").open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_official_validation_videos_become_the_held_out_test_split(tmp_path: Path) -> None:
    output = tmp_path / "out"
    prepare(*_sources(tmp_path), output, val_fraction=0.25, seed=42)

    test = _manifest(output, "test")
    # "other" (7) and "not annotated" (-1) are dropped; codes map to Mirror labels.
    assert [(row["label"], row["split"]) for row in test] == [("neutral", "test"), ("sad", "test")]
    assert (output / "images" / test[1]["path"]).read_bytes() == b"jpeg-bytes-v0/00001.jpg"


def test_training_videos_are_split_by_video_never_by_frame(tmp_path: Path) -> None:
    output = tmp_path / "out"
    report = prepare(*_sources(tmp_path), output, val_fraction=0.25, seed=42)

    def videos(split: str) -> set[str]:
        return {Path(row["path"]).name.split("_")[0] for row in _manifest(output, split)}

    assert videos("train").isdisjoint(videos("val"))
    assert (report["train"]["videos"], report["val"]["videos"]) == (3, 1)


def test_output_uses_the_fer2013_evaluation_contract(tmp_path: Path) -> None:
    output = tmp_path / "out"
    prepare(*_sources(tmp_path), output)

    metadata = json.loads((output / "metadata" / "transform_spec.json").read_text())
    assert metadata["class_order"] == [
        "angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"
    ]
    assert metadata["inference_transform"]["resize"] == [224, 224]


def test_refuses_to_overwrite_an_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    with pytest.raises(FileExistsError):
        prepare(*_sources(tmp_path), output)
