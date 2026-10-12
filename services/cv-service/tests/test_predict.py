from io import BytesIO

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

LABELS = ("angry", "disgust", "fear", "happy", "neutral", "sad", "surprise")


def jpeg_bytes() -> bytes:
    image = Image.new("RGB", (48, 48), color=(200, 200, 200))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.mark.anyio
async def test_predict_returns_normal_no_face_response() -> None:
    from app.main import create_app

    app = create_app(model_loader=object, face_detector=lambda image: None)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/predict",
            files={"image": ("scene.jpg", jpeg_bytes(), "image/jpeg")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["face_found"] is False
    assert body["probs"] == {}
    assert body["top2"] == []
    assert body["margin"] is None
    assert body["uncertain"] is None
    assert body["model_version"] == "cv-vit-b16-v3"
    assert isinstance(body["latency_ms"], float)


@pytest.mark.anyio
async def test_predict_returns_top_two_probabilities_for_a_detected_face() -> None:
    from app.main import create_app

    probabilities = {
        "angry": 0.03,
        "disgust": 0.01,
        "fear": 0.05,
        "happy": 0.10,
        "neutral": 0.31,
        "sad": 0.46,
        "surprise": 0.04,
    }
    app = create_app(
        model_loader=object,
        face_detector=lambda image: np.ones((48, 48, 3), dtype=np.uint8),
        classifier=lambda face: probabilities,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/predict",
            files={"image": ("face.jpg", jpeg_bytes(), "image/jpeg")},
        )

    assert response.status_code == 200
    assert response.json() | {"latency_ms": 0.0} == {
        "face_found": True,
        "probs": probabilities,
        "top2": [["sad", 0.46], ["neutral", 0.31]],
        "margin": 0.15,
        "uncertain": False,
        "model_version": "cv-vit-b16-v3",
        "latency_ms": 0.0,
    }


@pytest.mark.anyio
async def test_predict_rejects_unreadable_jpeg_sample() -> None:
    from app.main import create_app

    app = create_app(model_loader=object, face_detector=lambda image: None)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/predict",
            files={"image": ("broken.jpg", b"not a JPEG", "image/jpeg")},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "image is unreadable"
