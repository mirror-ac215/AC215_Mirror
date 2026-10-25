"""Training loop: train one epoch, validate, keep the best epoch, save a checkpoint."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch import nn


def train_one_epoch(model: nn.Module, loader: Iterable, criterion: nn.Module,
                    optimizer: torch.optim.Optimizer, device: torch.device,
                    max_batches: int | None = None, amp: bool = False) -> tuple[float, float]:
    """One pass over the training data. Labels may be soft (Mixup/CutMix): accuracy uses their argmax.

    amp=True computes in bfloat16 where safe (about 2x faster on a recent NVIDIA GPU).
    """
    model.train()
    total_loss, correct, seen = 0.0, 0, 0
    for step, (images, labels) in enumerate(loader):
        if max_batches is not None and step >= max_batches:
            break
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        with torch.autocast(device.type, dtype=torch.bfloat16, enabled=amp):
            logits = model(images)
            loss = criterion(logits.float(), labels)
        loss.backward()
        optimizer.step()
        hard = labels.argmax(dim=1) if labels.dim() == 2 else labels
        total_loss += loss.item() * images.size(0)
        correct += (logits.argmax(dim=1) == hard).sum().item()
        seen += images.size(0)
    return total_loss / max(seen, 1), correct / max(seen, 1)


@torch.no_grad()
def evaluate(model: nn.Module, loader: Iterable, device: torch.device,
             max_batches: int | None = None, amp: bool = False) -> dict[str, float]:
    """Validation with plain cross-entropy on hard labels; also macro-F1, our model-selection metric."""
    model.eval()
    criterion = nn.CrossEntropyLoss(reduction="sum")
    total_loss, y_true, y_pred = 0.0, [], []
    for step, (images, labels) in enumerate(loader):
        if max_batches is not None and step >= max_batches:
            break
        images, labels = images.to(device), labels.to(device)
        with torch.autocast(device.type, dtype=torch.bfloat16, enabled=amp):
            logits = model(images).float()
        total_loss += criterion(logits, labels).item()
        y_true.append(labels.cpu().numpy())
        y_pred.append(logits.argmax(dim=1).cpu().numpy())
    y_true_all, y_pred_all = np.concatenate(y_true), np.concatenate(y_pred)
    return {
        "loss": total_loss / len(y_true_all),
        "accuracy": float((y_true_all == y_pred_all).mean()),
        "macro_f1": float(f1_score(y_true_all, y_pred_all, average="macro", zero_division=0)),
    }


def fit(model: nn.Module, train_loader: Iterable, val_loader: Iterable, criterion: nn.Module,
        optimizer: torch.optim.Optimizer, scheduler: Any, device: torch.device, epochs: int,
        early_stopping_patience: int | None = None, max_batches: int | None = None,
        on_epoch: Callable[[dict[str, float]], None] | None = None, select_by: str = "val_accuracy",
        amp: bool = False, monitor: dict[str, Iterable] | None = None) -> dict[str, Any]:
    """Train for `epochs` and keep the weights of the best epoch by `select_by`
    (val_accuracy, as the baseline did, or val_macro_f1). `monitor` loaders are only scored and
    logged each epoch (e.g. FER-2013 val, to watch for forgetting); they never pick the epoch."""
    history: list[dict[str, float]] = []
    best = {"val_accuracy": -1.0, "val_macro_f1": -1.0, "epoch": 0}
    best_state: dict[str, torch.Tensor] | None = None
    best_loss, stale = float("inf"), 0
    for epoch in range(1, epochs + 1):
        train_loss, train_acc = train_one_epoch(model, train_loader, criterion, optimizer, device, max_batches, amp)
        val = evaluate(model, val_loader, device, max_batches, amp)
        if scheduler is not None:
            scheduler.step(val["loss"])
        row = {"epoch": epoch, "train_loss": train_loss, "train_accuracy": train_acc,
               "val_loss": val["loss"], "val_accuracy": val["accuracy"], "val_macro_f1": val["macro_f1"]}
        for name, loader in (monitor or {}).items():
            row[f"monitor_{name}_macro_f1"] = evaluate(model, loader, device, max_batches, amp)["macro_f1"]
        history.append(row)
        print(f"epoch {epoch}/{epochs} train_loss={train_loss:.4f} val_loss={val['loss']:.4f} "
              f"val_acc={val['accuracy']:.4f} val_macro_f1={val['macro_f1']:.4f}", flush=True)
        if on_epoch is not None:
            on_epoch(row)
        if row[select_by] > best[select_by]:
            best = {"val_accuracy": val["accuracy"], "val_macro_f1": val["macro_f1"], "epoch": epoch}
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        if early_stopping_patience is not None:
            stale = 0 if val["loss"] < best_loss - 1e-4 else stale + 1
            best_loss = min(best_loss, val["loss"])
            if stale >= early_stopping_patience:
                print(f"early stopping at epoch {epoch}", flush=True)
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    return {"history": history, "best": best}


def save_checkpoint(path: Path, model: nn.Module, result: dict[str, Any], class_order: list[str],
                    model_version: str, params: dict[str, Any]) -> None:
    """Same keys as the inherited vit_b16_v3_best.pth, so cv-service and cv-eval load it unchanged."""
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_name": model_version,
        "model_state_dict": model.state_dict(),
        "history": result["history"],
        "best_val_acc": result["best"]["val_accuracy"],
        "best_epoch": result["best"]["epoch"],
        "classes": class_order,
        "params": params,
    }, path)
