"""The baseline architecture: ImageNet ViT-B/16 with a new 7-class head."""

from __future__ import annotations

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
