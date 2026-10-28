from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image

from mirror_data_preprocess.ferplus import majority, prepare

VOTE_HEADER = "neutral,happiness,surprise,sadness,anger,disgust,fear,contempt,unknown,NF"


def _face(seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, (48, 48), dtype=np.uint8)


def _sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Three FER-2013 rows (one training, two test) and our matching train and test images."""
    # (Usage, original emotion code, face seed, FER+ votes)
    table = [
        ("Training", 3, 0, "0,10,0,0,0,0,0,0,0,0"),
        ("PublicTest", 4, 1, "8,0,0,2,0,0,0,0,0,0"),  # FER "sad", crowd says neutral
        ("PrivateTest", 3, 2, "5,5,0,0,0,0,0,0,0,0"),  # tie between neutral and happy
    ]
    fer2013 = tmp_path / "fer2013.csv"
    fer2013.write_text(
        "emotion,pixels,Usage\n"
        + "".join(f"{code},{' '.join(map(str, _face(seed).ravel()))},{usage}\n"
                  for usage, code, seed, _ in table),
        encoding="utf-8",
    )
    ferplus = tmp_path / "fer2013new.csv"
    ferplus.write_text(
        f"Usage,Image name,{VOTE_HEADER}\n"
        + "".join(f"{usage},fer{i:07d}.png,{votes}\n" for i, (usage, *_, votes) in enumerate(table)),
        encoding="utf-8",
    )

    fer_dir = tmp_path / "fer2013" / "v1"
    ours = {
        "train": [("Training_0.jpg", "happy", 0)],
        "val": [],
        "test": [("PublicTest_1.jpg", "sad", 1), ("PrivateTest_2.jpg", "happy", 2)],
    }
    (fer_dir / "manifests").mkdir(parents=True)
    for split, images in ours.items():
        for name, label, seed in images:
            path = fer_dir / "images" / split / label / name
            path.parent.mkdir(parents=True)
            noisy = np.clip(_face(seed).astype(int) + 1, 0, 255).astype(np.uint8)  # like JPEG noise
            Image.fromarray(noisy).save(path, format="PNG")
        (fer_dir / "manifests" / f"{split}.csv").write_text(
            "path,label,split\n"
            + "".join(f"{split}/{label}/{name},{label},{split}\n" for name, label, _ in images),
            encoding="utf-8",
        )
    (fer_dir / "metadata").mkdir()
    (fer_dir / "metadata" / "transform_spec.json").write_text(
        json.dumps({"class_order": ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]})
    )
    return fer_dir, fer2013, ferplus


def _manifest(output: Path, split: str) -> list[dict[str, str]]:
    with (output / "manifests" / f"{split}.csv").open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_majority_reports_ties() -> None:
    assert majority([8, 0, 0, 2, 0, 0, 0, 0, 0, 0]) == "neutral"
    assert majority([5, 5, 0, 0, 0, 0, 0, 0, 0, 0]) == "tie"


def test_images_get_the_crowd_label_and_vote_counts(tmp_path: Path) -> None:
    output = tmp_path / "out"
    report = prepare(*_sources(tmp_path), output)

    test = _manifest(output, "test")
    # The PublicTest image was "sad" in FER-2013; FER+'s 10 annotators say neutral (8 vs 2 sad).
    assert [(row["path"], row["label"]) for row in test] == [("test/neutral/PublicTest_1.jpg", "neutral")]
    assert (test[0]["votes_neutral"], test[0]["votes_sad"], test[0]["votes_happy"]) == ("8", "2", "0")
    assert report["outcome"] == {
        "train: kept": 1,
        "test: kept": 1,
        "test: relabelled": 1,
        "test: no Mirror label (tie/contempt/unknown/NF)": 1,
    }


def test_training_images_are_matched_to_training_rows_only(tmp_path: Path) -> None:
    output = tmp_path / "out"
    prepare(*_sources(tmp_path), output)

    train = _manifest(output, "train")
    assert [(row["path"], row["label"], row["votes_happy"]) for row in train] == [
        ("train/happy/Training_0.jpg", "happy", "10")
    ]
    assert _manifest(output, "val") == []


def test_an_image_that_matches_no_row_is_counted_not_guessed(tmp_path: Path) -> None:
    fer_dir, fer2013, ferplus = _sources(tmp_path)
    image = fer_dir / "images" / "test" / "sad" / "PublicTest_1.jpg"
    Image.fromarray(_face(99)).save(image, format="PNG")  # a different face

    report = prepare(fer_dir, fer2013, ferplus, tmp_path / "out")

    assert report["outcome"]["test: unmatched"] == 1

