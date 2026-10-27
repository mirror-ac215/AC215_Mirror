"""Training loop: train one epoch, validate, keep the best epoch, save a checkpoint."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch import nn


class WeightEMA:
    """A running average of the model's weights, updated after every batch:
    average = decay * average + (1 - decay) * current. With EMA on, the averaged weights are
    what gets scored, selected and saved: steadier than any single moment of training."""

    def __init__(self, model: nn.Module, decay: float) -> None:
        self.decay = decay
        self.average = {k: v.detach().clone() for k, v in model.state_dict().items()}

    @torch.no_grad()
    def update(self, model: nn.Module) -> None:
        for name, value in model.state_dict().items():
            if value.dtype.is_floating_point:
                self.average[name].lerp_(value, 1.0 - self.decay)
            else:
                self.average[name].copy_(value)

    @contextmanager
    def applied(self, model: nn.Module) -> Iterator[None]:
        """Temporarily put the averaged weights into the model, then restore the live ones."""
        live = {k: v.detach().clone() for k, v in model.state_dict().items()}
        model.load_state_dict(self.average)
        try:
            yield
        finally:
            model.load_state_dict(live)


def train_one_epoch(model: nn.Module, loader: Iterable, criterion: nn.Module,
                    optimizer: torch.optim.Optimizer, device: torch.device,
                    max_batches: int | None = None, amp: bool = False, step_scheduler: Any = None, ema: WeightEMA | None = None) -> tuple[float, float]:
    """One pass over the training data. Labels may be soft (Mixup/CutMix): accuracy uses their argmax.

    amp=True computes in bfloat16 where safe (about 2x faster on a recent NVIDIA GPU).
        step_scheduler, if given, moves the learning rate after every batch (cosine schedule).
    """
    model.train()
    if getattr(model, "frozen_backbone", False):
        model.eval()  # frozen layers keep their BatchNorm statistics; only the head learns
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
        if step_scheduler is not None:
            step_scheduler.step()
        if ema is not None:
            ema.update(model)
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


# Metrics that can pick the best epoch; early stopping may also watch the validation loss.
SELECT_METRICS = ("val_accuracy", "val_macro_f1")
STOP_METRICS = (*SELECT_METRICS, "val_loss")


def fit(model: nn.Module, train_loader: Iterable, val_loader: Iterable, criterion: nn.Module,
        optimizer: torch.optim.Optimizer, scheduler: Any, device: torch.device, epochs: int,
        early_stopping_patience: int | None = None, max_batches: int | None = None,
        on_epoch: Callable[[dict[str, float]], None] | None = None, select_by: str = "val_accuracy",
        amp: bool = False, monitor: dict[str, Iterable] | None = None,
        ema_decay: float | None = None, stop_by: str | None = None) -> dict[str, Any]:
    """Train for `epochs` and keep the weights of the best epoch by `select_by`
    (val_accuracy, as the baseline did, or val_macro_f1). `monitor` loaders are only scored and
    logged each epoch (e.g. FER-2013 val, to watch for forgetting); they never pick the epoch.
    Early stopping watches `stop_by`, which defaults to `select_by`, so a run can't stop while the
    number that picks the best epoch is still improving."""
    history: list[dict[str, float]] = []
    best = {"val_accuracy": -1.0, "val_macro_f1": -1.0, "epoch": 0}
    best_state: dict[str, torch.Tensor] | None = None
    stop_by = stop_by or select_by
    sign = -1.0 if stop_by == "val_loss" else 1.0  # loss: lower is better; accuracy and F1: higher
    best_stop, stale = float("-inf"), 0
    # ReduceLROnPlateau reacts to val loss once per epoch; any other scheduler moves every batch.
    per_epoch = isinstance(scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau)
    ema = WeightEMA(model, ema_decay) if ema_decay else None
    for epoch in range(1, epochs + 1):
        lr = optimizer.param_groups[-1]["lr"]  # the head's lr (the top one, with layer decay)
        train_loss, train_acc = train_one_epoch(model, train_loader, criterion, optimizer, device, max_batches,
                                                amp, None if per_epoch else scheduler, ema)
        # With EMA, the averaged weights are scored, selected and saved (the live ones keep training).
        with ema.applied(model) if ema is not None else nullcontext():
            val = evaluate(model, val_loader, device, max_batches, amp)
            row = {"epoch": epoch, "lr": lr, "train_loss": train_loss, "train_accuracy": train_acc,
                   "val_loss": val["loss"], "val_accuracy": val["accuracy"], "val_macro_f1": val["macro_f1"]}
            for name, loader in (monitor or {}).items():
                row[f"monitor_{name}_macro_f1"] = evaluate(model, loader, device, max_batches, amp)["macro_f1"]
            if row[select_by] > best[select_by]:
                best = {"val_accuracy": val["accuracy"], "val_macro_f1": val["macro_f1"], "epoch": epoch}
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        if scheduler is not None and per_epoch:
            scheduler.step(val["loss"])
        history.append(row)
        print(f"epoch {epoch}/{epochs} train_loss={train_loss:.4f} val_loss={val['loss']:.4f} "
              f"val_acc={val['accuracy']:.4f} val_macro_f1={val['macro_f1']:.4f}", flush=True)
        if on_epoch is not None:
            on_epoch(row)
        if early_stopping_patience is not None:
            score = sign * row[stop_by]
            stale = 0 if score > best_stop + 1e-4 else stale + 1
            best_stop = max(best_stop, score)
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
