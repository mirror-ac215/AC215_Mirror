from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
import torch.nn.functional as F
import yaml

from mirror_cv_train.data import (
    MixupCutmixCollator,
    build_eval_transform,
    build_mixed_sampler,
    build_train_transform,
    build_weighted_sampler,
    compute_class_weights,
)
from mirror_cv_train.losses import FocalLoss
from mirror_cv_train.model import build_vit

PARAMS = yaml.safe_load((Path(__file__).parents[1] / "params.yaml").read_text(encoding="utf-8"))


def test_focal_loss_with_gamma_zero_equals_cross_entropy() -> None:
    logits, target = torch.randn(8, 7), torch.randint(0, 7, (8,))
    assert torch.allclose(FocalLoss(gamma=0.0)(logits, target), F.cross_entropy(logits, target), atol=1e-6)


def test_focal_loss_down_weights_easy_examples() -> None:
    confident = torch.tensor([[8.0, 0, 0, 0, 0, 0, 0]])
    target = torch.tensor([0])
    assert FocalLoss(gamma=2.0)(confident, target) < F.cross_entropy(confident, target)


def test_focal_loss_accepts_soft_mixup_labels() -> None:
    soft = torch.full((4, 7), 1 / 7)
    assert FocalLoss(gamma=2.0, label_smoothing=0.1)(torch.randn(4, 7), soft).item() > 0


def test_sqrt_class_weights_favour_rare_classes_and_average_one() -> None:
    labels = np.array([0] * 90 + [1] * 10)
    weights = compute_class_weights(labels, 2, "sqrt")
    assert weights[1] > weights[0]
    assert weights.mean().item() == pytest.approx(1.0)


def test_sampler_draws_rare_class_more_often_than_its_share() -> None:
    labels = np.array([0] * 90 + [1] * 10)
    sampler = build_weighted_sampler(labels, 2, strength=0.5, generator=torch.Generator().manual_seed(0))
    drawn = labels[list(sampler)]
    assert len(drawn) == 100 and (drawn == 1).mean() > 0.10


def test_collator_returns_soft_labels_that_sum_to_one() -> None:
    collate = MixupCutmixCollator(7, prob=1.0, mixup_ratio=0.5, mixup_alpha=0.2, cutmix_alpha=1.0, seed=0)
    images, soft = collate([(torch.rand(3, 32, 32), i % 7) for i in range(6)])
    assert images.shape == (6, 3, 32, 32) and soft.shape == (6, 7)
    assert torch.allclose(soft.sum(dim=1), torch.ones(6))


def test_transforms_turn_a_grey_48px_face_into_a_normalised_224px_rgb_tensor() -> None:
    from PIL import Image

    face = Image.new("L", (48, 48), color=128)
    for transform in (build_train_transform(PARAMS), build_eval_transform(PARAMS)):
        assert transform(face).shape == (3, 224, 224)


def test_vit_head_matches_what_cv_service_loads() -> None:
    model = build_vit(num_classes=7, head_dropout=0.5, pretrained=False)
    assert isinstance(model.heads.head[0], torch.nn.Dropout)
    assert model.heads.head[1].in_features == 768 and model.heads.head[1].out_features == 7


def test_mixed_sampler_gives_each_source_its_share() -> None:
    big = np.zeros(900, dtype=np.int64)       # source A: 900 images
    small = np.zeros(100, dtype=np.int64)     # source B: 100 images
    sampler = build_mixed_sampler([big, small], [0.5, 0.5], num_classes=7, strength=0.5,
                                  generator=torch.Generator().manual_seed(0))
    drawn = np.array(list(sampler))
    assert len(drawn) == 1000
    assert 0.45 < (drawn >= 900).mean() < 0.55   # half the draws from the small source


def test_mixed_sampler_with_share_zero_never_draws_that_source() -> None:
    sampler = build_mixed_sampler([np.zeros(50, dtype=np.int64), np.zeros(50, dtype=np.int64)],
                                  [1.0, 0.0], num_classes=7, strength=0.5)
    assert max(sampler) < 50


def test_cosine_schedule_warms_up_then_decays_to_the_floor() -> None:
    from mirror_cv_train.cli import build_scheduler

    optimizer = torch.optim.SGD([torch.zeros(1, requires_grad=True)], lr=1.0)
    scheduler = build_scheduler(optimizer, {"name": "cosine", "warmup_fraction": 0.1, "min_lr_ratio": 0.01},
                                total_steps=100)
    lrs = []
    for _ in range(100):
        lrs.append(optimizer.param_groups[0]["lr"])
        optimizer.step()
        scheduler.step()
    assert lrs[0] == pytest.approx(0.1)          # warm-up starts low
    assert max(lrs) == pytest.approx(1.0)        # peaks at optimizer.lr after warm-up
    assert lrs[-1] < 0.02                        # ends near the 1 % floor
    assert lrs[10:] == sorted(lrs[10:], reverse=True)  # never rises after warm-up


def test_unknown_scheduler_is_rejected() -> None:
    from mirror_cv_train.cli import build_scheduler

    optimizer = torch.optim.SGD([torch.zeros(1, requires_grad=True)], lr=1.0)
    with pytest.raises(ValueError, match="unknown scheduler"):
        build_scheduler(optimizer, {"name": "cosin"}, total_steps=10)

def test_weight_ema_averages_and_can_be_swapped_in_and_out() -> None:
    from mirror_cv_train.train import WeightEMA

    model = torch.nn.Linear(1, 1, bias=False)
    with torch.no_grad():
        model.weight.fill_(0.0)
    ema = WeightEMA(model, decay=0.9)
    with torch.no_grad():
        model.weight.fill_(1.0)
    ema.update(model)
    assert ema.average["weight"].item() == pytest.approx(0.1)  # 0.9 * 0 + 0.1 * 1

    with ema.applied(model):
        assert model.weight.item() == pytest.approx(0.1)        # scored with the average
    assert model.weight.item() == pytest.approx(1.0)            # live weights restored
