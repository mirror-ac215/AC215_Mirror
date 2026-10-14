"""Run reproducible batch evaluation of the inherited CV checkpoint."""
from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter

import torch
from PIL import Image
from torchvision import models, transforms

from mirror_cv_eval.metrics import evaluate_predictions
from mirror_cv_eval.report import build_report
from mirror_cv_eval.tracking import log_aggregate_report


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    command.add_argument("--data-dir", type=Path, required=True)
    command.add_argument("--checkpoint", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--code-revision", required=True)
    command.add_argument("--batch-size", type=int, default=32)
    command.add_argument("--wandb-project", help="Optionally log aggregate metrics and configuration to this W&B project")
    return command


def transform_from_metadata(specification: dict[str, object]) -> transforms.Compose:
    """Build the evaluation transform from the dataset's recorded contract."""
    try:
        channels = int(specification["grayscale_to_channels"])
        height, width = (int(value) for value in specification["resize"])
        pixel_range = tuple(float(value) for value in specification["pixel_range"])
        mean = tuple(float(value) for value in specification["mean"])
        std = tuple(float(value) for value in specification["std"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("inference_transform metadata is invalid") from exc
    if channels != 3 or height <= 0 or width <= 0:
        raise ValueError("evaluation requires a positive RGB inference transform")
    if pixel_range != (0.0, 1.0) or len(mean) != 3 or len(std) != 3 or any(value == 0 for value in std):
        raise ValueError("inference_transform is incompatible with ToTensor RGB evaluation")
    return transforms.Compose(
        [
            transforms.Resize((height, width)),
            transforms.ToTensor(),
            transforms.Normalize(mean=mean, std=std),
        ]
    )


def _vit_b16_factory() -> torch.nn.Module:
    model = models.vit_b_16(weights=None)
    model.heads.head = torch.nn.Sequential(torch.nn.Dropout(0.5), torch.nn.Linear(768, 7))
    return model


def load_model(
    checkpoint: Path, *, model_factory: Callable[[], torch.nn.Module] = _vit_b16_factory
) -> torch.nn.Module:
    model = model_factory()
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if not isinstance(state, dict):
        raise TypeError("checkpoint must contain a state dictionary")
    state = state.get("state_dict", state.get("model_state_dict", state))
    if not isinstance(state, dict):
        raise TypeError("checkpoint state dictionary is invalid")
    model.load_state_dict({str(k).removeprefix("module."): v for k, v in state.items()}, strict=True)
    return model.eval()


def run(args: argparse.Namespace) -> int:
    metadata = json.loads((args.data_dir / "metadata" / "transform_spec.json").read_text())
    labels = tuple(metadata["class_order"])
    transform = transform_from_metadata(metadata["inference_transform"])
    rows = list(csv.DictReader((args.data_dir / "manifests" / "test.csv").open()))
    if not rows or any(row["label"] not in labels or row["split"] != "test" for row in rows):
        raise ValueError("test manifest is empty or violates the FER-2013 evaluation contract")
    model = load_model(args.checkpoint)
    y_true: list[str] = []
    y_pred: list[str] = []
    top2: list[tuple[str, ...]] = []
    started = perf_counter()
    with torch.inference_mode():
        for offset in range(0, len(rows), args.batch_size):
            batch_rows = rows[offset:offset + args.batch_size]
            batch = torch.stack([transform(Image.open(args.data_dir / "images" / row["path"]).convert("L").convert("RGB")) for row in batch_rows])
            probabilities = torch.softmax(model(batch), dim=1)
            for row, values in zip(batch_rows, probabilities, strict=True):
                ranked = torch.argsort(values, descending=True)[:2].tolist()
                y_true.append(row["label"])
                y_pred.append(labels[ranked[0]])
                top2.append(tuple(labels[index] for index in ranked))
    metrics = evaluate_predictions(labels=labels, y_true=tuple(y_true), y_pred=tuple(y_pred), top2=tuple(top2))
    report = build_report(model_uri=metadata["checkpoint"], model_version="cv-vit-b16-v3", dataset_version="fer2013/v1", code_revision=args.code_revision, class_order=labels, transform=metadata["inference_transform"], threshold=0.64, metrics=metrics)
    report["runtime"] = {"seconds": round(perf_counter() - started, 3), "batch_size": args.batch_size}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.wandb_project:
        log_aggregate_report(report, project=args.wandb_project)
    print(json.dumps({"output": str(args.output), "macro_f1": metrics.macro_f1, "passed": report["regression_guard"]["passed"]}))
    return 0 if report["regression_guard"]["passed"] else 2


def main(argv: Sequence[str] | None = None) -> int:
    return run(parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
