"""M4-26: the YuNet download is pinned, checked and cleaned up. No network: local files."""

import hashlib
import io
from pathlib import Path

import pytest

from app import fetch_models

GOOD = b"stand-in for the pinned model"
GOOD_SHA = hashlib.sha256(GOOD).hexdigest()


def leftovers(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.name.endswith(".part"))


def source(tmp_path: Path, data: bytes) -> str:
    path = tmp_path / "source.onnx"
    path.write_bytes(data)
    return path.as_uri()


def test_the_download_is_pinned_to_an_opencv_zoo_commit() -> None:
    assert len(fetch_models.OPENCV_ZOO_COMMIT) == 40
    assert f"/{fetch_models.OPENCV_ZOO_COMMIT}/" in fetch_models.YUNET_URL
    assert fetch_models.YUNET_URL.startswith("https://")
    assert fetch_models.YUNET_URL.endswith("/" + fetch_models.runtime.YUNET_MODEL.name)


def test_a_missing_file_is_downloaded_and_checked(tmp_path: Path) -> None:
    target = tmp_path / "models" / "yunet.onnx"
    fetch_models.ensure_yunet(target, source(tmp_path, GOOD), GOOD_SHA)
    assert target.read_bytes() == GOOD
    assert leftovers(target.parent) == []


def test_a_correct_file_is_kept_without_downloading(tmp_path: Path) -> None:
    target = tmp_path / "yunet.onnx"
    target.write_bytes(GOOD)
    fetch_models.ensure_yunet(target, "https://invalid.example/never-called", GOOD_SHA)
    assert target.read_bytes() == GOOD


def test_an_existing_corrupt_file_is_replaced(tmp_path: Path) -> None:
    target = tmp_path / "yunet.onnx"
    target.write_bytes(b"truncated")
    fetch_models.ensure_yunet(target, source(tmp_path, GOOD), GOOD_SHA)
    assert target.read_bytes() == GOOD
    assert leftovers(tmp_path) == []


def test_an_existing_corrupt_file_is_removed_even_if_the_download_fails(tmp_path: Path) -> None:
    target = tmp_path / "yunet.onnx"
    target.write_bytes(b"truncated")
    with pytest.raises(RuntimeError, match="sha256"):
        fetch_models.ensure_yunet(target, source(tmp_path, b"another file"), GOOD_SHA)
    assert not target.exists()
    assert leftovers(tmp_path) == []


def test_a_download_with_the_wrong_hash_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "models" / "yunet.onnx"
    with pytest.raises(RuntimeError, match="sha256"):
        fetch_models.ensure_yunet(target, source(tmp_path, b"another file"), GOOD_SHA)
    assert not target.exists()
    assert leftovers(target.parent) == []


def test_a_failed_connection_leaves_nothing_behind(tmp_path: Path) -> None:
    target = tmp_path / "yunet.onnx"
    with pytest.raises(OSError):
        fetch_models.ensure_yunet(target, (tmp_path / "missing.onnx").as_uri(), GOOD_SHA)
    assert not target.exists()
    assert leftovers(tmp_path) == []


def test_a_transfer_cut_off_midway_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CutOff(io.RawIOBase):
        def __init__(self) -> None:
            self.sent = False

        def readinto(self, buffer) -> int:
            if self.sent:
                raise ConnectionResetError("connection dropped")
            self.sent = True
            buffer[:4] = b"half"
            return 4

        def __enter__(self):
            return self

    monkeypatch.setattr(fetch_models.urllib.request, "urlopen", lambda *a, **k: CutOff())
    target = tmp_path / "yunet.onnx"
    with pytest.raises(ConnectionResetError):
        fetch_models.ensure_yunet(target, "https://example.invalid/yunet.onnx", GOOD_SHA)
    assert not target.exists()
    assert leftovers(tmp_path) == []
