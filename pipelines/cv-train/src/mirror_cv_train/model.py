"""The baseline architecture: ImageNet ViT-B/16 with a new 7-class head."""

from __future__ import annotations

from pathlib import Path

import torch
from torch import nn
from torchvision import models


def build_vit(num_classes: int, head_dropout: float, pretrained: bool = True) -> nn.Module:
    """Same head as cv-service and cv-eval load: Dropout + Linear(768, num_classes).

    Every layer is trainable (full fine-tuning with a small learning rate).
    """
    weights = models.ViT_B_16_Weights.DEFAULT if pretrained else None
    model = models.vit_b_16(weights=weights)
    model.heads.head = nn.Sequential(nn.Dropout(p=head_dropout), nn.Linear(model.heads.head.in_features, num_classes))
    for parameter in model.parameters():
        parameter.requires_grad = True
    return model


def load_init_checkpoint(model: nn.Module, path: Path) -> nn.Module:
    """Start from an earlier checkpoint (e.g. cv-vit-b16-v3) instead of plain ImageNet weights."""
    state = torch.load(path, map_location="cpu", weights_only=True)
    state = state.get("model_state_dict", state)
    model.load_state_dict({str(k).removeprefix("module."): v for k, v in state.items()}, strict=True)
    return model