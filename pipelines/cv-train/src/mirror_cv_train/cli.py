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
from torch.utils.data import ConcatDataset, DataLoader

from mirror_cv_train.data import (
    ManifestDataset,
    MixupCutmixCollator,
    build_eval_transform,
    build_mixed_sampler,
    build_train_transform,
    compute_class_weights,
    read_class_order,
)
from mirror_cv_train.losses import FocalLoss
from mirror_cv_train.model import build_vit, load_init_checkpoint
from mirror_cv_train.train import (
    SELECT_METRICS,
    STOP_METRICS,
    evaluate,
    fit,
    save_checkpoint,
)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Train Mirror's facial-expression model (M2-17).")
    command.add_argument("--params", type=Path, required=True, help="params.yaml with the recipe")
    command.add_argument("--data-dir", type=Path, help="one dataset, e.g. data/processed/fer2013/v1 (dvc pull)")
    command.add_argument("--data-root", type=Path,
                         help="folder holding the data.sources dirs of params.yaml (several datasets)")
    command.add_argument("--init-checkpoint", type=Path,
                         help="start from this checkpoint (e.g. vit_b16_v3_best.pth) instead of ImageNet")
    command.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                         help="override one params value, e.g. data.sources.fer2013.share=0 (repeatable)")
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


def apply_override(params: dict, assignment: str) -> None:
    """'a.b.c=value' sets params['a']['b']['c']; the value is parsed as YAML (0.5, true, null...)."""
    key, _, value = assignment.partition("=")
    *parents, leaf = key.split(".")
    node = params
    for name in parents:
        node = node[name]
    if leaf not in node:
        raise KeyError(f"--set {key}: no such params key")
    node[leaf] = yaml.safe_load(value)


def resolve_sources(params: dict, args: argparse.Namespace) -> tuple[dict[str, Path], dict, str]:
    """(dir per source, source settings, validation source). One --data-dir = one source, share 1."""
    sources = params["data"].get("sources")
    if sources is None:
        if args.data_dir is None:
            raise SystemExit("--data-dir is required (params.yaml has no data.sources)")
        return {"main": args.data_dir}, {"main": {"share": 1.0, "every_nth": 1}}, "main"
    if args.data_root is None:
        raise SystemExit("--data-root is required when params.yaml lists data.sources")
    dirs = {name: args.data_root / source["dir"] for name, source in sources.items()}
    return dirs, sources, params["data"]["val_source"]


def run(args: argparse.Namespace) -> dict[str, object]:
    params = yaml.safe_load(args.params.read_text(encoding="utf-8"))
    for assignment in args.set:
        apply_override(params, assignment)
    if args.epochs is not None:
        params["training"]["epochs"] = args.epochs
    if args.no_pretrained:
        params["model"]["pretrained"] = False
    # Check the metric names now: a typo would otherwise only fail after the first full epoch.
    select_by = params["training"].get("select_by", "val_accuracy")
    stop_by = params["training"].get("stop_by") or select_by
    if select_by not in SELECT_METRICS:
        raise SystemExit(f"training.select_by must be one of {SELECT_METRICS}, got {select_by!r}")
    if stop_by not in STOP_METRICS:
        raise SystemExit(f"training.stop_by must be one of {STOP_METRICS}, got {stop_by!r}")
    generator = seed_everything(int(params["training"]["seed"]))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    dirs, sources, val_source = resolve_sources(params, args)
    classes = read_class_order(dirs[val_source])
    if any(read_class_order(path) != classes for path in dirs.values()):
        raise ValueError("every source must use the same class_order")
    train_parts = [ManifestDataset(dirs[name], "train", classes, build_train_transform(params),
                                   every_nth=int(source.get("every_nth", 1)))
                   for name, source in sources.items()]
    train_ds = ConcatDataset(train_parts)
    train_labels = np.concatenate([part.labels for part in train_parts])
    eval_transform = build_eval_transform(params)
    val_ds = ManifestDataset(dirs[val_source], "val", classes, eval_transform)

    batch = int(params["data"]["batch_size"])
    mix = params["mixup"]
    collator = MixupCutmixCollator(len(classes), mix["prob"], mix["mixup_ratio"], mix["mixup_alpha"],
                                   mix["cutmix_alpha"], seed=int(params["training"]["seed"]))
    sampler = build_mixed_sampler([part.labels for part in train_parts],
                                  [float(source["share"]) for source in sources.values()],
                                  len(classes), params["imbalance"]["sampler_strength"], generator)
    train_loader = DataLoader(train_ds, batch_size=batch, sampler=sampler, collate_fn=collator)
    val_loader = DataLoader(val_ds, batch_size=batch, shuffle=False)
    # The other sources' val splits are only watched (forgetting), never used to pick the epoch.
    monitor = {name: DataLoader(ManifestDataset(path, "val", classes, eval_transform), batch_size=batch)
               for name, path in dirs.items() if name != val_source}
    test_loaders = {name: DataLoader(ManifestDataset(path, "test", classes, eval_transform), batch_size=batch)
                    for name, path in dirs.items()}

    pretrained = params["model"]["pretrained"] and args.init_checkpoint is None
    model = build_vit(len(classes), params["model"]["head_dropout"], pretrained)
    if args.init_checkpoint is not None:
        load_init_checkpoint(model, args.init_checkpoint)
        params["model"]["init_checkpoint"] = args.init_checkpoint.name  # recorded in W&B + checkpoint
    model = model.to(device)
    alpha = compute_class_weights(train_labels, len(classes), params["imbalance"]["class_weights"])
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
                 max_batches=args.max_batches, on_epoch=log.log if log else None,
                 select_by=select_by, stop_by=stop_by,
                 amp=bool(params["training"].get("amp", False)), monitor=monitor)
    # report_test: false keeps held-out test sets untouched until the final cv-eval run.
    tests = ({name: evaluate(model, loader, device, args.max_batches) for name, loader in test_loaders.items()}
             if params["training"].get("report_test", True) else {})
    version = f"{params['model']['name']}-{params['model']['version']}"
    save_checkpoint(args.output, model, result, classes, version, params)

    summary = {"model_version": version, "best_epoch": result["best"]["epoch"],
               "best_val_accuracy": result["best"]["val_accuracy"], "tests": tests,
               "checkpoint": str(args.output)}
    if log:
        for name, scores in tests.items():
            prefix = "test" if name == "main" else f"test_{name}"
            log.summary.update({f"{prefix}_accuracy": scores["accuracy"], f"{prefix}_macro_f1": scores["macro_f1"]})
        log.finish()
    print(json.dumps(summary, indent=2))
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    run(parser().parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
