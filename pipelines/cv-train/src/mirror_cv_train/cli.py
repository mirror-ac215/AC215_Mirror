"""mirror-cv-train: train the facial-expression model from params.yaml on the versioned dataset."""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import torch
import yaml
from torch.utils.data import DataLoader

from mirror_cv_train.data import (
    ManifestDataset,
    MixupCutmixCollator,
    build_eval_transform,
    build_train_transform,
    build_weighted_sampler,
    compute_class_weights,
    read_class_order,
)
from mirror_cv_train.losses import FocalLoss
from mirror_cv_train.model import build_vit
from mirror_cv_train.train import evaluate, fit, save_checkpoint


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Train Mirror's facial-expression model (M2-17).")
    command.add_argument("--params", type=Path, required=True, help="params.yaml with the recipe")
    command.add_argument("--data-dir", type=Path, required=True, help="data/processed/fer2013/v1 (dvc pull)")
    command.add_argument("--output", type=Path, required=True, help="where to write the checkpoint (.pth)")
    command.add_argument("--epochs", type=int, help="override training.epochs")
    command.add_argument("--max-batches", type=int, help="smoke run: stop each epoch after N batches")
    command.add_argument("--no-pretrained", action="store_true", help="skip the ImageNet download (smoke runs)")
    command.add_argument("--wandb-project", help="log per-epoch metrics and the config to this W&B project")
    return command


def seed_everything(seed: int) -> torch.Generator:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    return torch.Generator().manual_seed(seed)


def run(args: argparse.Namespace) -> dict[str, object]:
    params = yaml.safe_load(args.params.read_text(encoding="utf-8"))
    if args.epochs is not None:
        params["training"]["epochs"] = args.epochs
    if args.no_pretrained:
        params["model"]["pretrained"] = False
    generator = seed_everything(int(params["training"]["seed"]))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    classes = read_class_order(args.data_dir)
    train_ds = ManifestDataset(args.data_dir, "train", classes, build_train_transform(params))
    val_ds = ManifestDataset(args.data_dir, "val", classes, build_eval_transform(params))
    test_ds = ManifestDataset(args.data_dir, "test", classes, build_eval_transform(params))

    batch = int(params["data"]["batch_size"])
    mix = params["mixup"]
    collator = MixupCutmixCollator(len(classes), mix["prob"], mix["mixup_ratio"], mix["mixup_alpha"],
                                   mix["cutmix_alpha"], seed=int(params["training"]["seed"]))
    sampler = build_weighted_sampler(train_ds.labels, len(classes), params["imbalance"]["sampler_strength"], generator)
    train_loader = DataLoader(train_ds, batch_size=batch, sampler=sampler, collate_fn=collator)
    val_loader = DataLoader(val_ds, batch_size=batch, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=batch, shuffle=False)

    model = build_vit(len(classes), params["model"]["head_dropout"], params["model"]["pretrained"]).to(device)
    alpha = compute_class_weights(train_ds.labels, len(classes), params["imbalance"]["class_weights"])
    criterion = FocalLoss(params["loss"]["gamma"], alpha.to(device), params["loss"]["label_smoothing"])
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(params["optimizer"]["lr"]),
                                  weight_decay=float(params["optimizer"]["weight_decay"]))
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min",
                                                           factor=params["scheduler"]["factor"],
                                                           patience=params["scheduler"]["patience"])

    log = None
    if args.wandb_project:
        import wandb

        log = wandb.init(project=args.wandb_project, job_type="train", config=params)

    result = fit(model, train_loader, val_loader, criterion, optimizer, scheduler, device,
                 epochs=int(params["training"]["epochs"]),
                 early_stopping_patience=params["training"]["early_stopping_patience"],
                 max_batches=args.max_batches, on_epoch=log.log if log else None)
    test = evaluate(model, test_loader, device, args.max_batches)
    version = f"{params['model']['name']}-{params['model']['version']}"
    save_checkpoint(args.output, model, result, classes, version, params)

    summary = {"model_version": version, "best_epoch": result["best"]["epoch"],
               "best_val_accuracy": result["best"]["val_accuracy"], "test": test,
               "checkpoint": str(args.output)}
    if log:
        log.summary.update({"test_accuracy": test["accuracy"], "test_macro_f1": test["macro_f1"]})
        log.finish()
    print(json.dumps(summary, indent=2))
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    run(parser().parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
