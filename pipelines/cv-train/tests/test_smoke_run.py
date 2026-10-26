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
                 "--set", "data.sources.fer2013.share=0", "--set", "scheduler.name=cosine",
                 "--set", "training.ema_decay=0.99", "--set", "optimizer.layer_decay=0.75"]) == 0

    checkpoint = torch.load(out, map_location="cpu", weights_only=False)
    assert checkpoint["model_name"] == "cv-vit-b16-v4"
    assert checkpoint["params"]["model"]["init_checkpoint"] == "start.pth"
    assert checkpoint["params"]["data"]["sources"]["fer2013"]["share"] == 0
    assert "monitor_fer2013_macro_f1" in checkpoint["history"][0]
    assert checkpoint["params"]["scheduler"]["name"] == "cosine"
    assert checkpoint["history"][0]["lr"] > 0
    assert checkpoint["params"]["optimizer"]["layer_decay"] == 0.75


def test_a_misspelt_override_is_rejected(tmp_path: Path) -> None:
    from mirror_cv_train.cli import apply_override

    params = {"data": {"sources": {"fer2013": {"share": 0.5}}}}
    apply_override(params, "data.sources.fer2013.share=0.25")
    assert params["data"]["sources"]["fer2013"]["share"] == 0.25
    with pytest.raises(KeyError, match="no such params key"):
        apply_override(params, "data.sources.fer2013.shares=0")


def test_soft_labels_are_read_as_vote_shares(tmp_path: Path) -> None:
    from mirror_cv_train.data import (
        ManifestDataset,
        MixupCutmixCollator,
        build_eval_transform,
    )

    data = make_dataset(tmp_path / "data")
    manifest = data / "manifests" / "train.csv"
    with manifest.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    votes = {f"votes_{label}": 0 for label in CLASSES}
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "label", "split", *votes])
        writer.writeheader()
        writer.writerows([{**row, **votes, "votes_neutral": 8, "votes_sad": 2} for row in rows])
    transform = build_eval_transform({"data": {"image_size": 224}})

    soft = ManifestDataset(data, "train", CLASSES, transform, soft_labels=True)
    _, target = soft[0]
    assert target.tolist() == pytest.approx([0, 0, 0, 0, 0.8, 0.2, 0])

    hard = ManifestDataset(data, "train", CLASSES, transform)
    collator = MixupCutmixCollator(7, prob=0.0, mixup_ratio=0.5, mixup_alpha=0.2, cutmix_alpha=1.0, seed=0)
    _, targets = collator([soft[0], hard[0]])  # one FER+ photo and one hard-labelled frame
    assert targets[0].tolist() == pytest.approx([0, 0, 0, 0, 0.8, 0.2, 0])
    assert targets[1].tolist() == [1, 0, 0, 0, 0, 0, 0]

    with pytest.raises(ValueError, match="no soft-label columns"):
        ManifestDataset(data, "val", CLASSES, transform, soft_labels=True)

def test_efficientnet_trains_from_a_converted_checkpoint(tmp_path: Path) -> None:
    from mirror_cv_train.model import build_model

    root = tmp_path / "processed"
    make_dataset(root / "affwild2" / "v1")
    make_dataset(root / "fer2013" / "v1")
    start = tmp_path / "hsemotion.pth"
    torch.save({"model_state_dict": build_model("tf_efficientnet_b2", 7, 0.5, False, "max").state_dict()}, start)
    params = yaml.safe_load((Path(__file__).parents[1] / "params_m3-01.yaml").read_text(encoding="utf-8"))
    params["data"]["batch_size"] = 4
    params["training"]["amp"] = False
    (tmp_path / "params.yaml").write_text(yaml.safe_dump(params))
    out = tmp_path / "out" / "model.pth"

    assert main(["--params", str(tmp_path / "params.yaml"), "--data-root", str(root), "--output", str(out),
                 "--epochs", "1", "--max-batches", "1", "--init-checkpoint", str(start),
                 "--set", "model.architecture=tf_efficientnet_b2", "--set", "model.global_pool=max",
                 "--set", "data.image_size=64", "--set", "model.name=cv-enet-b2"]) == 0

    checkpoint = torch.load(out, map_location="cpu", weights_only=False)
    assert checkpoint["model_name"] == "cv-enet-b2-v4"
    assert checkpoint["model_state_dict"]["classifier.weight"].shape == (7, 1408)


def test_unknown_architecture_is_rejected() -> None:
    from mirror_cv_train.model import build_model

    with pytest.raises(ValueError, match="unknown architecture"):
        build_model("resnet50", 7, 0.5, False)




def test_train_only_head_leaves_every_feature_layer_unchanged(tmp_path: Path) -> None:
    from mirror_cv_train.model import build_model

    root = tmp_path / "processed"
    make_dataset(root / "affwild2" / "v1")
    make_dataset(root / "fer2013" / "v1")
    start = tmp_path / "start.pth"
    before = build_model("tf_efficientnet_b2", 7, 0.5, False, "max").state_dict()
    torch.save({"model_state_dict": before}, start)
    params = yaml.safe_load((Path(__file__).parents[1] / "params_m3-01.yaml").read_text(encoding="utf-8"))
    params["data"]["batch_size"] = 4
    params["training"]["amp"] = False
    (tmp_path / "params.yaml").write_text(yaml.safe_dump(params))
    out = tmp_path / "out" / "model.pth"

    assert main(["--params", str(tmp_path / "params.yaml"), "--data-root", str(root), "--output", str(out),
                 "--epochs", "1", "--max-batches", "2", "--init-checkpoint", str(start),
                 "--set", "model.architecture=tf_efficientnet_b2", "--set", "model.global_pool=max",
                 "--set", "data.image_size=64", "--set", "model.train_only_head=true",
                 "--set", "optimizer.lr=0.1"]) == 0

    after = torch.load(out, map_location="cpu", weights_only=False)["model_state_dict"]
    changed = [name for name in before if not torch.equal(before[name], after[name])]
    assert changed and all(name.startswith("classifier.") for name in changed)  # incl. BatchNorm stats