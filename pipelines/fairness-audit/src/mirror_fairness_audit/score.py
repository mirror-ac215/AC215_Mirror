"""Score every FairFace photo the way cv-service scores a webcam frame.

Same steps as services/cv-service/app/runtime.py: Haar face detection (largest face),
grayscale -> 3 channels, 224x224, ImageNet normalisation, ViT-B/16 with 7 outputs.
When Haar finds no face, cv-service would answer "no face"; the audit records that
(face_found = False) and still scores the whole photo, which lets the model's own
behaviour be compared on every photo.

Output: one CSV row per photo with its groups and the 7 probabilities. No image or
crop is ever written.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np

from mirror_fairness_audit import LABELS
from mirror_fairness_audit.fairface import Photo

FIELDS = ("file", "race", "gender", "age", "face_found", *LABELS)


def build_model() -> Any:
    import torch
    from torchvision import models

    model = models.vit_b_16(weights=None)
    model.heads.head = torch.nn.Sequential(
        torch.nn.Dropout(p=0.5),
        torch.nn.Linear(model.heads.head.in_features, len(LABELS)),
    )
    return model


def load_model(checkpoint: Path, device: str = "cpu") -> Any:
    import torch

    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if isinstance(state, dict):
        state = state.get("state_dict", state.get("model_state_dict", state))
    model = build_model()
    model.load_state_dict({str(k).removeprefix("module."): v for k, v in state.items()})
    return model.to(device).eval()


class FaceDetector:
    """cv-service's detector: the largest Haar face, or None."""

    def __init__(self) -> None:
        import cv2

        self._cv2 = cv2
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._cascade = cv2.CascadeClassifier(path)
        if self._cascade.empty():
            raise RuntimeError(f"could not load Haar cascade at {path}")

    def __call__(self, image: np.ndarray) -> np.ndarray | None:
        gray = self._cv2.cvtColor(image, self._cv2.COLOR_RGB2GRAY)
        faces = self._cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
        )
        if len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda f: int(f[2]) * int(f[3]))
        return image[y : y + h, x : x + w]


def to_tensor(face: np.ndarray) -> Any:
    from PIL import Image
    from torchvision import transforms

    transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ]
    )
    return transform(Image.fromarray(face).convert("L").convert("RGB"))


def score(
    photos: Iterable[Photo],
    images_dir: Path,
    model: Any,
    detector: Any,
    *,
    device: str = "cpu",
    batch_size: int = 64,
) -> Iterable[dict[str, Any]]:
    """Yield one result row per photo, in batches for speed."""
    import torch
    from PIL import Image

    def flush(batch: list[tuple[Photo, bool, Any]]) -> list[dict[str, Any]]:
        with torch.inference_mode():
            logits = model(torch.stack([t for _, _, t in batch]).to(device))
            probs = torch.softmax(logits, dim=1).cpu().tolist()
        if len(probs[0]) != len(LABELS):
            raise RuntimeError(f"model returned {len(probs[0])} classes; expected {len(LABELS)}")
        return [
            {
                "file": p.file,
                "race": p.race,
                "gender": p.gender,
                "age": p.age,
                "face_found": found,
                **{label: round(v, 6) for label, v in zip(LABELS, row, strict=True)},
            }
            for (p, found, _), row in zip(batch, probs, strict=True)
        ]

    batch: list[tuple[Photo, bool, Any]] = []
    for photo in photos:
        image = np.asarray(Image.open(images_dir / photo.file).convert("RGB"))
        face = detector(image)
        batch.append((photo, face is not None, to_tensor(image if face is None else face)))
        if len(batch) == batch_size:
            yield from flush(batch)
            batch = []
    if batch:
        yield from flush(batch)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(rows: Iterable[dict[str, Any]], output: Path, meta: dict[str, Any]) -> int:
    """predictions.csv plus predictions.meta.json (which model, which labels file)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    meta = {**meta, "photos_scored": count, "predictions_sha256": sha256(output)}
    output.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return count
