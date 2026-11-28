"""Download the YuNet face detector from opencv_zoo, pinned by commit and sha256.

Model files are not committed to this repository. The Docker build runs this module
(``python -m app.fetch_models``). The unit tests never download: they use a stand-in file
and a stand-in detector; tests/test_yunet_artifact.py checks the real download and is
opt-in (MIRROR_MODEL_DOWNLOAD_TESTS=1).

The download goes to a temporary file next to the target and only replaces the target
once its sha256 matches. A wrong hash, a failed or interrupted transfer, or any other
error leaves no temporary file behind. An existing target with the wrong hash is deleted
before downloading, so it can never be used.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path

from app import runtime

OPENCV_ZOO_COMMIT = "f12e12798e8314f7c074a6656816c048dcc95b7a"
YUNET_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
    f"{OPENCV_ZOO_COMMIT}/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_yunet(
    path: Path = runtime.YUNET_MODEL, url: str = YUNET_URL, expected_sha256: str | None = None
) -> Path:
    """Return ``path`` holding the pinned model, downloading it if missing or invalid."""
    expected = expected_sha256 or runtime.YUNET_SHA256
    if path.is_file():
        if sha256_of(path) == expected:
            return path
        path.unlink()  # wrong hash (corrupt, partial or another version): never kept
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".part")
    partial = Path(name)
    try:
        with os.fdopen(handle, "wb") as out, urllib.request.urlopen(url, timeout=60) as response:
            shutil.copyfileobj(response, out)
        digest = sha256_of(partial)
        if digest != expected:
            raise RuntimeError(f"downloaded YuNet has sha256 {digest}, expected {expected}")
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)
    return path


if __name__ == "__main__":
    print(ensure_yunet())
