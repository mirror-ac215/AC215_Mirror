from __future__ import annotations

import numpy as np
import pytest

from mirror_cv_eval.crop_protocol import (
    CropBox,
    crop_with_margin,
    validate_manifest_row,
)


def test_crop_with_margin_expands_a_face_box_and_clips_to_image_bounds():
    image = np.zeros((100, 100, 3), dtype=np.uint8)

    crop = crop_with_margin(image, CropBox(x=5, y=5, width=20, height=20), margin=0.15)

    assert crop.shape == (26, 26, 3)


def test_crop_with_margin_rejects_a_box_outside_the_image():
    image = np.zeros((20, 20, 3), dtype=np.uint8)

    with pytest.raises(ValueError, match="inside image bounds"):
        crop_with_margin(image, CropBox(x=19, y=0, width=2, height=2), margin=0.15)


def test_manifest_row_requires_a_label_and_face_box_coordinates():
    with pytest.raises(ValueError, match="missing required fields"):
        validate_manifest_row({"path": "frame.jpg", "label": "happy"})
