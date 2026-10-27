"""Protocol helpers for evaluating live-frame Haar crop variants.

This module deliberately has no detector or model dependency. The evaluation
manifest supplies independently verified face boxes so both transforms consume
exactly the same labelled face region.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

_REQUIRED_FIELDS = frozenset({"path", "label", "x", "y", "width", "height"})


@dataclass(frozen=True)
class CropBox:
    x: int
    y: int
    width: int
    height: int


def validate_manifest_row(row: Mapping[str, str]) -> CropBox:
    """Validate one labelled live-frame manifest row and return its face box."""
    missing = sorted(_REQUIRED_FIELDS - set(row))
    if missing:
        raise ValueError(f"manifest row missing required fields: {', '.join(missing)}")
    if not row["path"] or not row["label"]:
        raise ValueError("manifest path and label must be non-empty")
    try:
        box = CropBox(*(int(row[name]) for name in ("x", "y", "width", "height")))
    except ValueError as exc:
        raise ValueError("face box coordinates must be integers") from exc
    if box.x < 0 or box.y < 0 or box.width <= 0 or box.height <= 0:
        raise ValueError("face box coordinates must be non-negative with positive dimensions")
    return box


def crop_with_margin(image: np.ndarray, box: CropBox, *, margin: float) -> np.ndarray:
    """Crop a face box with proportional margin, clipping only the added margin."""
    if not 0.0 <= margin <= 1.0:
        raise ValueError("margin must be between 0.0 and 1.0")
    height, width = image.shape[:2]
    if box.x + box.width > width or box.y + box.height > height:
        raise ValueError("face box must be inside image bounds")
    x_padding = round(box.width * margin)
    y_padding = round(box.height * margin)
    left = max(0, box.x - x_padding)
    top = max(0, box.y - y_padding)
    right = min(width, box.x + box.width + x_padding)
    bottom = min(height, box.y + box.height + y_padding)
    return image[top:bottom, left:right]
