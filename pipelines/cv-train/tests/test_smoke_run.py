"""End-to-end smoke run on a tiny fake dataset in the real layout (no download, CPU, seconds)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import torch
import yaml
from PIL import Image

from mirror_cv_train.cli import main

CLASSES = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]


def make_dataset(root: Path) -> Path:
    (root / "metadata").mkdir(parents=True)
    (root / "metadata" / "transform_spec.json").write_text(json.dumps({"class_order": CLASSES}))
    (root / "manifests").mkdir()
    for split in ("train", "val", "test"):
        rows = []
        for i, label in enumerate(CLASSES):
            path = f"{split}/{label}/{i}.png"
            (root / "images" / split / label).mkdir(parents=True, exist_ok=True)
            Image.new("L", (48, 48), color=20 + 30 * i).save(root / "images" / path)
            rows.append({"path": path, "label": label, "split": split})
        with (root / "manifests" / f"{split}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["path", "label", "split"])
            writer.writeheader()
            writer.writerows(rows)
    return root


def test_one_epoch_writes_a_checkpoint_cv_service_can_read(tmp_path: Path) -> None:
    data = make_dataset(tmp_path / "data")
    params = yaml.safe_load((Path(__file__).parents[1] / "params.yaml").read_text(encoding="utf-8"))
    params["data"]["batch_size"] = 4
    (tmp_path / "params.yaml").write_text(yaml.safe_dump(params))
    out = tmp_path / "out" / "model.pth"

    assert main(["--params", str(tmp_path / "params.yaml"), "--data-dir", str(data), "--output", str(out),
                 "--epochs", "1", "--max-batches", "1", "--no-pretrained"]) == 0

    checkpoint = torch.load(out, map_location="cpu", weights_only=False)
    assert checkpoint["classes"] == CLASSES
    assert checkpoint["model_name"] == "cv-vit-b16-v3"
    assert checkpoint["model_state_dict"]["heads.head.1.weight"].shape == (7, 768)


def test_unknown_label_in_manifest_is_rejected(tmp_path: Path) -> None:
    from mirror_cv_train.data import ManifestDataset, build_eval_transform

    data = make_dataset(tmp_path / "data")
    with pytest.raises(ValueError, match="outside class_order"):
        ManifestDataset(data, "train", CLASSES[:-1], build_eval_transform({"data": {"image_size": 224}}))
