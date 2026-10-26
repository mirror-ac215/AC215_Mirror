"""Model architectures: the baseline ViT-B/16 (torchvision) and timm EfficientNets (e.g. HSEmotion)."""

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


def build_model(architecture: str, num_classes: int, head_dropout: float, pretrained: bool = True,
                global_pool: str = "avg") -> nn.Module:
    """vit_b_16: the baseline above. tf_efficientnet_*: a timm EfficientNet, e.g. tf_efficientnet_b2 with
    global_pool="max" to start from HSEmotion's AffectNet weights (converted, see the README)."""
    if architecture == "vit_b_16":
        return build_vit(num_classes, head_dropout, pretrained)
    if architecture.startswith("tf_efficientnet_"):
        import timm

        return timm.create_model(architecture, pretrained=pretrained, num_classes=num_classes,
                                 drop_rate=head_dropout, global_pool=global_pool)
    raise ValueError(f"unknown architecture: {architecture}")


def freeze_all_but_head(model: nn.Module) -> nn.Module:
    """Linear probe: only the final classifier learns; every feature layer keeps the loaded weights.
    frozen_backbone tells the training loop to keep BatchNorm statistics frozen too."""
    head = model.heads if hasattr(model, "heads") else model.get_classifier()
    for parameter in model.parameters():
        parameter.requires_grad = False
    for parameter in head.parameters():
        parameter.requires_grad = True
    model.frozen_backbone = True
    return model


def load_init_checkpoint(model: nn.Module, path: Path) -> nn.Module:
    """Start from an earlier checkpoint (e.g. cv-vit-b16-v3) instead of plain ImageNet weights."""
    state = torch.load(path, map_location="cpu", weights_only=True)
    state = state.get("model_state_dict", state)
    model.load_state_dict({str(k).removeprefix("module."): v for k, v in state.items()}, strict=True)
    return model