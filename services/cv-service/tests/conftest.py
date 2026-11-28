"""Shared test setup. Unit tests are hermetic: no network, no real YuNet model.

`stub_yunet` gives a stand-in model file (its hash is made the expected one) and makes
OpenCV return `FixedYuNet`, which reports the detection rows a test sets. The real pinned
download and the real model are checked only in tests/test_yunet_artifact.py (opt-in).
"""

import hashlib
import urllib.request
from pathlib import Path

import numpy as np
import pytest

from app import runtime


class FixedYuNet:
    """Stands in for cv2.FaceDetectorYN: returns the given rows, records its inputs."""

    def __init__(self, rows: list[list[float]] | None = None) -> None:
        self.rows = rows or []
        self.input_size: tuple[int, int] | None = None
        self.created_with: tuple | None = None

    def setInputSize(self, size: tuple[int, int]) -> None:  # OpenCV's method name
        self.input_size = size

    def detect(self, image: np.ndarray) -> tuple[int, np.ndarray | None]:
        if not self.rows:
            return 0, None
        return len(self.rows), np.array(self.rows, dtype=np.float32)


class StubYuNet:
    def __init__(self, path: Path, detector: FixedYuNet) -> None:
        self.path = path
        self.detector = detector


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Fails any test that tries an internet download (opt-in artifact tests excepted)."""
    if request.node.get_closest_marker("network"):
        return

    def refuse(url, *args, **kwargs):
        if str(getattr(url, "full_url", url)).startswith("file:"):
            return real_urlopen(url, *args, **kwargs)
        raise AssertionError(f"unit tests must not download: {url}")

    real_urlopen = urllib.request.urlopen
    monkeypatch.setattr(urllib.request, "urlopen", refuse)


@pytest.fixture
def stub_yunet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StubYuNet:
    model = tmp_path / "face_detection_yunet_2023mar.onnx"
    model.write_bytes(b"stand-in for the YuNet model")
    monkeypatch.setattr(runtime, "YUNET_SHA256", hashlib.sha256(model.read_bytes()).hexdigest())
    detector = FixedYuNet()

    class FakeFaceDetectorYN:
        @staticmethod
        def create(*args):
            detector.created_with = args
            return detector

    monkeypatch.setattr(runtime.cv2, "FaceDetectorYN", FakeFaceDetectorYN)
    return StubYuNet(model, detector)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "network: downloads the real pinned model (opt-in)")
