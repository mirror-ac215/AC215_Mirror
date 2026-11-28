"""M4-26 integration (opt-in): the real pinned YuNet download and the real model.

Needs the internet, so the unit suite skips it. Run it with

    MIRROR_MODEL_DOWNLOAD_TESTS=1 uv run pytest tests/test_yunet_artifact.py

It downloads into a temporary folder (the checkout is not changed), checks the sha256
from app/runtime.py, loads the model with OpenCV and runs it on a blank frame.
"""

import os
from pathlib import Path

import numpy as np
import pytest

from app import fetch_models
from app.runtime import YUNET_SHA256, FaceDetector

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.environ.get("MIRROR_MODEL_DOWNLOAD_TESTS") != "1",
        reason="set MIRROR_MODEL_DOWNLOAD_TESTS=1 to download the real model",
    ),
]


def test_the_pinned_download_has_the_expected_hash_and_runs(tmp_path: Path) -> None:
    model = fetch_models.ensure_yunet(tmp_path / "face_detection_yunet_2023mar.onnx")
    assert fetch_models.sha256_of(model) == YUNET_SHA256
    assert model.stat().st_size == 232_589
    detector = FaceDetector(model_path=model)
    assert detector(np.full((240, 320, 3), 128, dtype=np.uint8)) is None
