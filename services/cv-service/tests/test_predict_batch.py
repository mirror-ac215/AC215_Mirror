from io import BytesIO

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image


def jpeg_bytes() -> bytes:
    image = Image.new("RGB", (48, 48), color=(200, 200, 200))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.mark.anyio
async def test_predict_batch_returns_a_no_face_result_for_each_input() -> None:
    from app.main import create_app

    app = create_app(model_loader=object, face_detector=lambda image: None)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/predict_batch",
            files=[
                ("images", ("scene-1.jpg", jpeg_bytes(), "image/jpeg")),
                ("images", ("scene-2.jpg", jpeg_bytes(), "image/jpeg")),
            ],
        )

    assert response.status_code == 200
    assert response.json()["predictions"] == [
        {
            "face_found": False,
            "probs": {},
            "top2": [],
            "margin": None,
            "uncertain": None,
            "model_version": "cv-vit-b16-v3",
            "latency_ms": pytest.approx(response.json()["predictions"][0]["latency_ms"]),
        },
        {
            "face_found": False,
            "probs": {},
            "top2": [],
            "margin": None,
            "uncertain": None,
            "model_version": "cv-vit-b16-v3",
            "latency_ms": pytest.approx(response.json()["predictions"][1]["latency_ms"]),
        },
    ]


@pytest.mark.anyio
async def test_predict_batch_rejects_more_than_eight_images() -> None:
    from app.main import create_app

    app = create_app(model_loader=object, face_detector=lambda image: None)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/predict_batch",
            files=[
                ("images", (f"scene-{index}.jpg", jpeg_bytes(), "image/jpeg"))
                for index in range(9)
            ],
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "batch contains more than 8 images"
