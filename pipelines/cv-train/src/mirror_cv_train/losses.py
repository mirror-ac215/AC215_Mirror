"""Focal loss that accepts hard or soft (Mixup/CutMix) labels."""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


class FocalLoss(nn.Module):
    """Multi-class focal loss with optional per-class alpha and label smoothing.

    gamma > 0 down-weights easy, confident examples, so the rare and hard classes
    (disgust, fear, sad on FER-2013) get more of the gradient.
    """

    def __init__(self, gamma: float = 2.0, alpha: torch.Tensor | None = None,
                 label_smoothing: float = 0.0) -> None:
        super().__init__()
        self.gamma = gamma
        self.label_smoothing = label_smoothing
        self.register_buffer("alpha", alpha.float() if alpha is not None else None)

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        log_probs = F.log_softmax(logits, dim=-1)
        num_classes = logits.size(-1)
        if target.dim() == 1:
            target = F.one_hot(target, num_classes).to(log_probs.dtype)
        target = target.to(log_probs.dtype)
        if self.label_smoothing > 0:
            target = target * (1.0 - self.label_smoothing) + self.label_smoothing / num_classes
        loss = -((1.0 - log_probs.exp()) ** self.gamma) * log_probs * target
        if self.alpha is not None:
            loss = loss * self.alpha.unsqueeze(0)
        return loss.sum(dim=-1).mean()
