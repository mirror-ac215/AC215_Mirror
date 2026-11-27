"""M4-26: the "face found" path through the real FaceDetector and /predict.

No face images are stored in this public repository, so YuNet's own detect() is
replaced by a fixed detection row (x, y, w, h, 10 landmark values, score). Everything
after that is the real code: the largest-face choice, the square crop, the bounds,
and the request path that hands the crop to the classifier.
"""

from io import BytesIO

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.runtime import FaceDetector

LABELS = ("angry", "disgust", "fear", "happy", "neutral", "sad", "surprise")


def row(x: float, y: float, w: float, h: float, score: float = 0.95) -> list[float]:
    return [x, y, w, h, *([0.0] * 10), score]


class FixedYuNet:
    """Stands in for cv2.FaceDetectorYN: returns the given rows, records the input size."""

    def __init__(self, rows: list[list[float]]) -> None:
        self.rows = np.array(rows, dtype=np.float32) if rows else None
        self.input_size: tuple[int, int] | None = None

    def setInputSize(self, size: tuple[int, int]) -> None:  # OpenCV's method name
        self.input_size = size

    def detect(self, image: np.ndarray) -> tuple[int, np.ndarray | None]:
        return (0 if self.rows is None else len(self.rows)), self.rows


def detector_with(rows: list[list[float]]) -> tuple[FaceDetector, FixedYuNet]:
    detector = FaceDetector()  # real model file, real hash check
    fake = FixedYuNet(rows)
    detector._detector = fake
    return detector, fake


def frame(height: int = 240, width: int = 320) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 0] = (np.arange(width) % 256).astype(np.uint8)[None, :]  # x is readable from red
    return image


def test_a_detected_face_gives_a_square_crop_inside_the_frame() -> None:
    detector, fake = detector_with([row(100, 60, 60, 80)])
    crop = detector(frame())
    assert fake.input_size == (320, 240)  # set to the frame's own size
    assert crop is not None
    assert crop.shape == (80, 80, 3)  # square, side = the longer box edge
    assert crop[0, 0, 0] == 90  # centred on the box: x from 130 - 40


def test_the_largest_of_several_faces_is_used() -> None:
    detector, _ = detector_with([row(10, 10, 30, 30), row(150, 50, 90, 90), row(250, 150, 40, 40)])
    crop = detector(frame())
    assert crop is not None
    assert crop.shape[:2] == (90, 90)
    assert crop[0, 0, 0] == 150


def test_a_face_at_the_edge_is_clipped_not_padded() -> None:
    detector, _ = detector_with([row(-20, 200, 60, 60)])
    crop = detector(frame())
    assert crop is not None
    assert crop.shape[:2] == (40, 40)  # rows 200-239, columns 0-39


def test_a_box_entirely_outside_the_frame_counts_as_no_face() -> None:
    detector, _ = detector_with([row(400, 300, 50, 50)])
    assert detector(frame()) is None


def test_no_detection_rows_means_no_face() -> None:
    detector, _ = detector_with([])
    assert detector(frame()) is None


@pytest.mark.anyio
async def test_predict_sends_the_detector_crop_to_the_classifier() -> None:
    from app.main import create_app

    detector, _ = detector_with([row(100, 60, 60, 80)])
    seen: list[tuple[int, ...]] = []

    def classifier(face: np.ndarray) -> dict[str, float]:
        seen.append(face.shape)
        return {label: (0.4 if label == "happy" else 0.1) for label in LABELS}

    app = create_app(model_loader=object, face_detector=detector, classifier=classifier)
    buffer = BytesIO()
    Image.fromarray(frame()).save(buffer, format="JPEG")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/predict", files={"image": ("frame.jpg", buffer.getvalue(), "image/jpeg")}
        )

    assert response.status_code == 200
    assert response.json()["face_found"] is True
    assert response.json()["top2"][0][0] == "happy"
    assert seen == [(80, 80, 3)]
