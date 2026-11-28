"""Shared test setup. Unit tests are hermetic: no network, no real YuNet model.

The real model is checked by cv-service's opt-in tests/test_yunet_artifact.py; a test here
keeps params.yaml's pinned URL, sha256 and threshold equal to cv-service's.
"""

import urllib.request

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(url, *args, **kwargs):
        raise AssertionError(f"unit tests must not download: {url}")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


@pytest.fixture
def no_face_yunet(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenCV's YuNet replaced by a detector that never finds a face."""
    import cv2

    class NoFaces:
        def setInputSize(self, size):  # OpenCV's method name
            pass

        def detect(self, image):
            return 0, None

    class FakeFaceDetectorYN:
        @staticmethod
        def create(*args):
            return NoFaces()

    monkeypatch.setattr(cv2, "FaceDetectorYN", FakeFaceDetectorYN)
