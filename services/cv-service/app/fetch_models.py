"""Download the YuNet face detector from opencv_zoo, pinned by commit and sha256.

Model files are not committed to this repository. The Docker build runs this module
(``python -m app.fetch_models``), the tests call ``ensure_yunet()`` when the file is
missing, and the fairness audit reads the same file. A download whose sha256 differs
from ``YUNET_SHA256`` is deleted and raises, so a changed upstream file can never be used.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

from app.runtime import YUNET_MODEL, YUNET_SHA256

OPENCV_ZOO_COMMIT = "f12e12798e8314f7c074a6656816c048dcc95b7a"
YUNET_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/"
    f"{OPENCV_ZOO_COMMIT}/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_yunet(path: Path = YUNET_MODEL, url: str = YUNET_URL) -> Path:
    """Return ``path``, downloading the model first if it is missing. Checks the sha256."""
    if path.exists() and sha256_of(path) == YUNET_SHA256:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=60) as response:
        partial.write_bytes(response.read())
    digest = sha256_of(partial)
    if digest != YUNET_SHA256:
        partial.unlink()
        raise RuntimeError(f"downloaded YuNet has sha256 {digest}, expected {YUNET_SHA256}")
    partial.replace(path)
    return path


if __name__ == "__main__":
    print(ensure_yunet())
