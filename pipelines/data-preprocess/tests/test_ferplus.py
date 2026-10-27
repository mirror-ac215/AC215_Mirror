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
    """Three FER-2013 rows (one training, two test) and our two test images."""
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
    ours = [("PublicTest_1.jpg", "sad", 1), ("PrivateTest_2.jpg", "happy", 2)]
    for name, label, seed in ours:
        path = fer_dir / "images" / "test" / label / name
        path.parent.mkdir(parents=True)
        noisy = np.clip(_face(seed).astype(int) + 1, 0, 255).astype(np.uint8)  # like JPEG noise
        Image.fromarray(noisy).save(path, format="PNG")
    (fer_dir / "manifests").mkdir()
    (fer_dir / "manifests" / "test.csv").write_text(
        "path,label,split\n"
        + "".join(f"test/{label}/{name},{label},test\n" for name, label, _ in ours),
        encoding="utf-8",
    )
    (fer_dir / "metadata").mkdir()
    (fer_dir / "metadata" / "transform_spec.json").write_text(
        json.dumps({"class_order": ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]})
    )
    return fer_dir, fer2013, ferplus


def test_majority_reports_ties() -> None:
    assert majority([8, 0, 0, 2, 0, 0, 0, 0, 0, 0]) == "neutral"
    assert majority([5, 5, 0, 0, 0, 0, 0, 0, 0, 0]) == "tie"


def test_images_get_the_crowd_label_and_ties_are_dropped(tmp_path: Path) -> None:
    output = tmp_path / "out"
    report = prepare(*_sources(tmp_path), output)

    with (output / "manifests" / "test.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    # The PublicTest image was "sad" in FER-2013; FER+'s 10 annotators say neutral.
    assert rows == [{"path": "test/neutral/PublicTest_1.jpg", "label": "neutral", "split": "test"}]
    assert report["outcome"] == {
        "kept": 1,
        "relabelled": 1,
        "no Mirror label (tie/contempt/unknown/NF)": 1,
    }


def test_an_image_that_matches_no_row_is_counted_not_guessed(tmp_path: Path) -> None:
    fer_dir, fer2013, ferplus = _sources(tmp_path)
    image = fer_dir / "images" / "test" / "sad" / "PublicTest_1.jpg"
    Image.fromarray(_face(99)).save(image, format="PNG")  # a different face

    report = prepare(fer_dir, fer2013, ferplus, tmp_path / "out")

    assert report["outcome"]["unmatched"] == 1
