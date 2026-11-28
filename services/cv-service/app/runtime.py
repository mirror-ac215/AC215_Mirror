"""CPU-only face detection and ViT-B/16 inference runtime."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from google.cloud import storage
from PIL import Image
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from torchvision import models, transforms

LABELS = ("angry", "disgust", "fear", "happy", "neutral", "sad", "surprise")


class ModelSettings(BaseSettings):
    """Model artifact location. Credentials are supplied by Application Default Credentials."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    model_bucket: str = "mirror-ac215-data"
    model_project: str = "mirror-ac215"
    model_object: str = "models/cv/v4/vit_b16_v4.pth"
    model_version: str = "cv-vit-b16-v4"
    model_cache_dir: Path = Path("/tmp/mirror-cv-model")
    max_batch_size: int = Field(default=8, ge=1, le=64)
    uncertain_margin: float = Field(default=0.1, ge=0.0, le=1.0)


# OpenCV's YuNet face detector (opencv_zoo, MIT licence). Not committed: app/fetch_models.py
# downloads it (pinned commit, sha256-checked) during the Docker build and for tests.
# M4-26 (PR #118): replaces the Haar cascade, which missed far more Black and older faces in the
# FairFace audit. The fairness audit loads the same file and checks the same hash.
YUNET_MODEL = Path(__file__).parent / "models" / "face_detection_yunet_2023mar.onnx"
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
FACE_SCORE_THRESHOLD = 0.9  # opencv_zoo's default for this model


def square_face_crop(image: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    """A square crop around the detector's box, like the Haar crops v4 was evaluated on."""
    height, width = image.shape[:2]
    x, y, box_width, box_height = box
    side = max(box_width, box_height)
    centre_x, centre_y = x + box_width / 2, y + box_height / 2
    left = max(0, round(centre_x - side / 2))
    top = max(0, round(centre_y - side / 2))
    right = min(width, round(centre_x + side / 2))
    bottom = min(height, round(centre_y + side / 2))
    return image[top:bottom, left:right]


class FaceDetector:
    """YuNet detector that returns the largest detected RGB face crop, or None."""

    def __init__(
        self,
        model_path: Path = YUNET_MODEL,
        score_threshold: float = FACE_SCORE_THRESHOLD,
    ) -> None:
        if not model_path.is_file():
            raise RuntimeError(f"face detector model not found at {model_path}")
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        if digest != YUNET_SHA256:
            raise RuntimeError(f"face detector model at {model_path} has sha256 {digest}")
        self._detector = cv2.FaceDetectorYN.create(
            str(model_path), "", (320, 320), score_threshold, 0.3, 5000
        )

    def __call__(self, image: np.ndarray) -> np.ndarray | None:
        height, width = image.shape[:2]
        self._detector.setInputSize((width, height))
        _, faces = self._detector.detect(cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        if faces is None or len(faces) == 0:
            return None
        x, y, box_width, box_height = max(faces, key=lambda face: face[2] * face[3])[:4]
        crop = square_face_crop(image, (x, y, box_width, box_height))
        return crop if crop.size else None


class ExpressionClassifier:
    """Applies the inherited model's grayscale-to-RGB ImageNet preprocessing."""

    _transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ]
    )

    def __init__(self, model: torch.nn.Module) -> None:
        self._model = model.to("cpu").eval()

    def __call__(self, face: np.ndarray) -> dict[str, float]:
        image = Image.fromarray(face).convert("L").convert("RGB")
        batch = self._transform(image).unsqueeze(0)
        with torch.inference_mode():
            logits = self._model(batch.to("cpu"))
            values = torch.softmax(logits, dim=1).squeeze(0).tolist()
        if len(values) != len(LABELS):
            raise RuntimeError(f"model returned {len(values)} classes; expected {len(LABELS)}")
        return {label: float(value) for label, value in zip(LABELS, values, strict=True)}


def _vit_b16_factory() -> torch.nn.Module:
    model = models.vit_b_16(weights=None)
    model.heads.head = torch.nn.Sequential(
        torch.nn.Dropout(p=0.5),
        torch.nn.Linear(model.heads.head.in_features, len(LABELS)),
    )
    return model


def _state_dict(checkpoint: object) -> dict[str, torch.Tensor]:
    if not isinstance(checkpoint, dict):
        raise RuntimeError("checkpoint must contain a state dictionary")  # noqa: TRY004
    state = checkpoint.get("state_dict", checkpoint.get("model_state_dict", checkpoint))
    if not isinstance(state, dict):
        raise RuntimeError("checkpoint state dictionary is invalid")  # noqa: TRY004
    return {
        str(key).removeprefix("module."): value
        for key, value in state.items()
        if isinstance(value, torch.Tensor)
    }


def load_model(
    settings: ModelSettings,
    *,
    storage_client_factory: Callable[..., Any] = storage.Client,
    model_factory: Callable[[], torch.nn.Module] = _vit_b16_factory,
) -> torch.nn.Module:
    """Download the configured checkpoint once at startup and load it on CPU."""
    settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = settings.model_cache_dir / Path(settings.model_object).name
    client = storage_client_factory(project=settings.model_project)
    client.bucket(settings.model_bucket).blob(settings.model_object).download_to_filename(
        str(checkpoint_path)
    )
    checkpoint = torch.load(checkpoint_path, map_location=torch.device("cpu"), weights_only=True)
    model = model_factory()
    try:
        model.load_state_dict(_state_dict(checkpoint), strict=True)
    except RuntimeError as exc:
        raise RuntimeError("checkpoint is incompatible with the 7-class ViT-B/16 model") from exc
    return model.to("cpu").eval()


def load_runtime(
    settings: ModelSettings | None = None,
    *,
    storage_client_factory: Callable[..., Any] = storage.Client,
) -> tuple[FaceDetector, ExpressionClassifier, str]:
    settings = settings or ModelSettings()
    return (
        FaceDetector(),
        ExpressionClassifier(load_model(settings, storage_client_factory=storage_client_factory)),
        settings.model_version,
    )
