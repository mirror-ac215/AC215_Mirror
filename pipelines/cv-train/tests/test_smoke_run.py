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
from mirror_cv_train.model import build_vit

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




def test_two_sources_start_from_a_checkpoint_and_record_it(tmp_path: Path) -> None:
    root = tmp_path / "processed"
    make_dataset(root / "affwild2" / "v1")
    make_dataset(root / "fer2013" / "v1")
    start = tmp_path / "start.pth"
    torch.save({"model_state_dict": build_vit(7, 0.5, pretrained=False).state_dict()}, start)
    params = yaml.safe_load((Path(__file__).parents[1] / "params_m3-01.yaml").read_text(encoding="utf-8"))
    params["data"]["batch_size"] = 4
    params["training"]["amp"] = False  # CI has no GPU
    (tmp_path / "params.yaml").write_text(yaml.safe_dump(params))
    out = tmp_path / "out" / "model.pth"

    assert main(["--params", str(tmp_path / "params.yaml"), "--data-root", str(root), "--output", str(out),
                 "--epochs", "1", "--max-batches", "1", "--init-checkpoint", str(start),
                 "--set", "data.sources.fer2013.share=0"]) == 0

    checkpoint = torch.load(out, map_location="cpu", weights_only=False)
    assert checkpoint["model_name"] == "cv-vit-b16-v4"
    assert checkpoint["params"]["model"]["init_checkpoint"] == "start.pth"
    assert checkpoint["params"]["data"]["sources"]["fer2013"]["share"] == 0
    assert "monitor_fer2013_macro_f1" in checkpoint["history"][0]


def test_a_misspelt_override_is_rejected(tmp_path: Path) -> None:
    from mirror_cv_train.cli import apply_override

    params = {"data": {"sources": {"fer2013": {"share": 0.5}}}}
    apply_override(params, "data.sources.fer2013.share=0.25")
    assert params["data"]["sources"]["fer2013"]["share"] == 0.25
    with pytest.raises(KeyError, match="no such params key"):
        apply_override(params, "data.sources.fer2013.shares=0")

def test_a_misspelt_select_by_fails_before_any_training(tmp_path: Path) -> None:
    # Julie (#56): a typo used to fail only after the first full epoch.
    params = yaml.safe_load((Path(__file__).parents[1] / "params.yaml").read_text(encoding="utf-8"))
    params["training"]["select_by"] = "val_macro_F1"
    (tmp_path / "params.yaml").write_text(yaml.safe_dump(params))
    with pytest.raises(SystemExit, match="select_by must be one of"):
        main(["--params", str(tmp_path / "params.yaml"), "--data-dir", str(tmp_path / "missing"),
              "--output", str(tmp_path / "model.pth")])


def test_early_stopping_watches_the_selection_metric_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # Julie (#56): val loss gets worse every epoch while macro-F1 keeps improving
    # (focal loss + class weights can do this). Stopping on the loss would end the run too early.
    from torch import nn

    from mirror_cv_train import train

    epochs = [{"loss": 1.0 + e, "accuracy": 0.5, "macro_f1": 0.2 + 0.1 * e} for e in range(3)]
    scores = iter(epochs + epochs)
    monkeypatch.setattr(train, "train_one_epoch", lambda *args, **kwargs: (0.0, 0.0))
    monkeypatch.setattr(train, "evaluate", lambda *args, **kwargs: next(scores))

    def run(**kwargs: str) -> dict:
        return train.fit(nn.Linear(1, 1), [], [], None, None, None, torch.device("cpu"), epochs=3,
                         early_stopping_patience=1, select_by="val_macro_f1", **kwargs)

    assert len(run()["history"]) == 3  # F1 still rising: runs to the end
    assert len(run(stop_by="val_loss")["history"]) == 2  # the old behaviour: stops after one worse loss
