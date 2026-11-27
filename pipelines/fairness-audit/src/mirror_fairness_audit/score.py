"""Score every FairFace photo the way cv-service scores a webcam frame.

Same steps as services/cv-service/app/runtime.py: YuNet face detection (largest face,
square crop), grayscale -> 3 channels, 224x224, ImageNet normalisation, ViT-B/16 with
7 outputs. When no face is found, cv-service would answer "no face"; the audit records that
(face_found = False) and still scores the whole photo, which lets the model's own
behaviour be compared on every photo.

Output: one CSV row per photo with its groups and the 7 probabilities. No image or
crop is ever written.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
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


def square_face_crop(image: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    """cv-service's crop: a square around the detector's box, clipped to the image."""
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
    """cv-service's detector: the largest YuNet face (square crop), or None.

    The model file and threshold come from params.yaml; a test keeps them equal to
    cv-service's. A model file with a different sha256 is refused.
    """

    def __init__(self, model_path: Path, sha256_expected: str, score_threshold: float) -> None:
        import cv2

        self._cv2 = cv2
        if not model_path.is_file():
            raise RuntimeError(f"face detector model not found at {model_path}")
        digest = sha256(model_path)
        if digest != sha256_expected:
            raise ValueError(
                f"{model_path} has sha256 {digest}, params.yaml expects {sha256_expected}"
            )
        self._detector = cv2.FaceDetectorYN.create(
            str(model_path), "", (320, 320), score_threshold, 0.3, 5000
        )

    def __call__(self, image: np.ndarray) -> np.ndarray | None:
        height, width = image.shape[:2]
        self._detector.setInputSize((width, height))
        _, faces = self._detector.detect(self._cv2.cvtColor(image, self._cv2.COLOR_RGB2BGR))
        if faces is None or len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])[:4]
        crop = square_face_crop(image, (x, y, w, h))
        return crop if crop.size else None


def detector_from_params(params: dict[str, Any], params_path: Path) -> FaceDetector:
    """The detector named in params.yaml; its model path is relative to params.yaml."""
    spec = params["detector"]
    return FaceDetector(
        (params_path.parent / spec["model"]).resolve(),
        spec["sha256"],
        float(spec["score_threshold"]),
    )


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


def check_output(path: Path) -> None:
    """Per-photo rows must never reach git: inside a repository, the file must be ignored."""
    path = path.resolve()
    repo = next((d for d in path.parents if (d / ".git").exists()), None)
    if repo is None:
        return
    check = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", str(path)], check=False)
    if check.returncode != 0:
        raise ValueError(
            f"{path} is inside the git repository and not ignored: "
            "write predictions to an outputs/ folder or outside the repository"
        )


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
