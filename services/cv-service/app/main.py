"""HTTP boundary for CPU facial-expression inference."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from io import BytesIO
from time import perf_counter
from typing import Any
from uuid import uuid4

import numpy as np
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError

from app.runtime import ModelSettings, load_runtime

DEFAULT_MODEL_VERSION = "cv-vit-b16-v3"
FaceDetector = Callable[[np.ndarray], np.ndarray | None]
Classifier = Callable[[np.ndarray], Mapping[str, float]]
logger = logging.getLogger("mirror.cv-service")


def create_app(
    model_loader: Callable[[], Any | None] | None = None,
    face_detector: FaceDetector | None = None,
    classifier: Classifier | None = None,
) -> FastAPI:
    """Create the service application with explicit model-readiness state."""
    settings = ModelSettings()

    @asynccontextmanager
    async def load_default_runtime_on_startup(application: FastAPI) -> AsyncIterator[None]:
        try:
            detector, loaded_classifier = load_runtime(settings)
        except Exception as exc:  # Keep the process observable; readiness stays false.
            application.state.model_load_error = str(exc)
            logger.exception("cv model startup failed")
        else:
            application.state.model = object()
            application.state.face_detector = detector
            application.state.classifier = loaded_classifier
        yield

    app = FastAPI(
        title="Mirror cv-service",
        lifespan=load_default_runtime_on_startup if model_loader is None else None,
    )
    app.state.model = model_loader() if model_loader is not None else None
    app.state.model_version = settings.model_version
    app.state.face_detector = face_detector
    app.state.classifier = classifier
    app.state.model_load_error = None
    app.state.requests_total = 0

    @app.middleware("http")
    async def log_request(request: Request, call_next: Any) -> Any:
        started = perf_counter()
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        app.state.requests_total += 1
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "latency_ms": round((perf_counter() - started) * 1000, 3),
                }
            )
        )
        return response

    @app.get("/health")
    def health() -> Any:
        if app.state.model is None:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unready",
                    "model_version": app.state.model_version,
                },
            )
        return {"status": "ok", "model_version": app.state.model_version}

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        return {
            "requests_total": app.state.requests_total,
            "model_ready": app.state.model is not None,
            "model_version": app.state.model_version,
        }

    @app.post("/predict")
    async def predict(image: UploadFile = File(...)) -> dict[str, Any]:
        started = perf_counter()
        if image.content_type != "image/jpeg":
            raise HTTPException(status_code=422, detail="image must be a JPEG")
        try:
            frame = np.asarray(Image.open(BytesIO(await image.read())).convert("RGB"))
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(status_code=422, detail="image is unreadable") from exc

        if app.state.face_detector is None:
            raise HTTPException(status_code=503, detail="face detection is not configured")
        face = app.state.face_detector(frame)
        latency_ms = round((perf_counter() - started) * 1000, 3)
        if face is None:
            return {
                "face_found": False,
                "probs": {},
                "top2": [],
                "margin": None,
                "uncertain": None,
                "model_version": app.state.model_version,
                "latency_ms": latency_ms,
            }
        if app.state.classifier is None:
            raise HTTPException(status_code=503, detail="classification is not configured")

        probabilities = dict(app.state.classifier(face))
        ranked = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
        if len(ranked) != 7:
            raise HTTPException(status_code=503, detail="model returned an invalid class count")
        top2 = [[label, probability] for label, probability in ranked[:2]]
        margin = round(top2[0][1] - top2[1][1], 6)
        return {
            "face_found": True,
            "probs": probabilities,
            "top2": top2,
            "margin": margin,
            "uncertain": margin < settings.uncertain_margin,
            "model_version": app.state.model_version,
            "latency_ms": round((perf_counter() - started) * 1000, 3),
        }

    return app


app = create_app()
