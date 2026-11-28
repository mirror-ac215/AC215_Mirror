"""M4-26: the YuNet download is pinned and refuses a file with the wrong sha256."""

from pathlib import Path

import pytest

from app import fetch_models
from app.runtime import YUNET_MODEL, YUNET_SHA256


def test_the_download_is_pinned_to_an_opencv_zoo_commit() -> None:
    assert fetch_models.OPENCV_ZOO_COMMIT in fetch_models.YUNET_URL
    assert len(fetch_models.OPENCV_ZOO_COMMIT) == 40
    assert fetch_models.YUNET_URL.startswith("https://")


def test_the_model_file_in_place_has_the_pinned_hash() -> None:
    assert fetch_models.sha256_of(YUNET_MODEL) == YUNET_SHA256


def test_an_existing_correct_file_is_not_downloaded_again(tmp_path: Path) -> None:
    target = tmp_path / "yunet.onnx"
    target.write_bytes(YUNET_MODEL.read_bytes())
    assert fetch_models.ensure_yunet(target, url="https://invalid.example/never-called") == target


def test_a_download_with_the_wrong_hash_is_refused_and_deleted(tmp_path: Path) -> None:
    source = tmp_path / "other.onnx"
    source.write_bytes(b"not the YuNet model")
    target = tmp_path / "models" / "yunet.onnx"
    with pytest.raises(RuntimeError, match="sha256"):
        fetch_models.ensure_yunet(target, url=source.as_uri())
    assert not target.exists()
    assert not target.with_suffix(".part").exists()
