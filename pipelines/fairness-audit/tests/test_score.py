"""Scoring with a stand-in model: cv-service's steps, batching, and what gets written."""

import csv
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from mirror_fairness_audit import LABELS
from mirror_fairness_audit.fairface import Photo
from mirror_fairness_audit.score import FaceDetector, build_model, score, to_tensor, write


class FixedModel(torch.nn.Module):
    """Always puts most weight on 'happy', whatever the photo."""

    def forward(self, batch: torch.Tensor) -> torch.Tensor:
        logits = torch.zeros(batch.shape[0], len(LABELS))
        logits[:, LABELS.index("happy")] = 3.0
        return logits


def test_the_real_architecture_has_seven_outputs() -> None:
    with torch.inference_mode():
        assert build_model().eval()(torch.zeros(1, 3, 224, 224)).shape == (1, 7)


def test_preprocessing_matches_cv_service() -> None:
    tensor = to_tensor(np.full((50, 40, 3), 128, dtype=np.uint8))
    assert tensor.shape == (3, 224, 224)
    assert torch.allclose(tensor[0], tensor[0].flatten()[0])  # grayscale: one value everywhere


def test_no_face_is_recorded_and_the_photo_still_scored(tmp_path: Path) -> None:
    (tmp_path / "val").mkdir()
    photos = []
    for i in range(5):
        Image.new("RGB", (224, 224), (i * 40, 90, 90)).save(tmp_path / f"val/{i}.jpg")
        photos.append(Photo(f"val/{i}.jpg", "White", "Female", "20-29"))
    rows = list(score(photos, tmp_path, FixedModel(), FaceDetector(), batch_size=2))
    assert len(rows) == 5
    assert all(r["face_found"] is False for r in rows)  # plain colour: Haar finds nothing
    assert all(max(LABELS, key=lambda label: r[label]) == "happy" for r in rows)
    assert abs(sum(rows[0][label] for label in LABELS) - 1) < 1e-4


def test_write_keeps_numbers_and_provenance_only(tmp_path: Path) -> None:
    rows = [
        {
            "file": "val/1.jpg",
            "race": "Black",
            "gender": "Male",
            "age": "30-39",
            "face_found": True,
            **{label: 1 / 7 for label in LABELS},
        }
    ]
    out = tmp_path / "predictions.csv"
    assert write(rows, out, {"model_version": "cv-vit-b16-v4"}) == 1
    with out.open() as handle:
        assert next(csv.DictReader(handle))["race"] == "Black"
    meta = json.loads(out.with_suffix(".meta.json").read_text())
    assert meta["photos_scored"] == 1 and len(meta["predictions_sha256"]) == 64
