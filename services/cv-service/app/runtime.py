"""CPU-only face detection and ViT-B/16 inference runtime."""

from __future__ import annotations

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
    model_object: str = "models/cv/inherited-v3/vit_b16_v3_best.pth"
    model_version: str = "cv-vit-b16-v3"
    model_cache_dir: Path = Path("/tmp/mirror-cv-model")
    max_batch_size: int = Field(default=8, ge=1, le=64)
    uncertain_margin: float = Field(default=0.1, ge=0.0, le=1.0)


class FaceDetector:
    """Haar-cascade detector that returns the largest detected RGB face crop."""

    def __init__(self) -> None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._cascade = cv2.CascadeClassifier(cascade_path)
        if self._cascade.empty():
            raise RuntimeError(f"could not load Haar cascade at {cascade_path}")

    def __call__(self, image: np.ndarray) -> np.ndarray | None:
        grayscale = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        faces = self._cascade.detectMultiScale(
            grayscale, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
        )
        if len(faces) == 0:
            return None
        x, y, width, height = max(faces, key=lambda face: int(face[2]) * int(face[3]))
        return image[y : y + height, x : x + width]


class ExpressionClassifier:
    """Applies the inherited model's grayscale-to-RGB ImageNet preprocessing."""

    _transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)
            ),
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
        ExpressionClassifier(
            load_model(settings, storage_client_factory=storage_client_factory)
        ),
        settings.model_version,
    )
