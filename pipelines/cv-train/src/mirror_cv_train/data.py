"""Data side of the baseline recipe: dataset, transforms, imbalance handling, Mixup/CutMix.

Reads the DVC-versioned FER-2013 v1 dataset (pipelines/data-preprocess):
  <data_dir>/manifests/{train,val,test}.csv  with columns path,label,split
  <data_dir>/images/<path>                    48x48 greyscale PNGs
  <data_dir>/metadata/transform_spec.json     class_order (index = model output)
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import Dataset, WeightedRandomSampler
from torchvision import transforms

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def read_class_order(data_dir: Path) -> list[str]:
    spec = json.loads((data_dir / "metadata" / "transform_spec.json").read_text(encoding="utf-8"))
    return list(spec["class_order"])


class ManifestDataset(Dataset):
    """One split of the versioned dataset. Returns (image tensor, class index)."""

    def __init__(self, data_dir: Path, split: str, class_order: Sequence[str],
                 transform: Callable[[Image.Image], torch.Tensor], every_nth: int = 1) -> None:
        manifest = data_dir / "manifests" / f"{split}.csv"
        with manifest.open(encoding="utf-8", newline="") as handle:
            # Manifests are sorted by label then file, so [::n] keeps every n-th row of each label: roughly
            # every n-th frame of each video, but the count carries over from one video to the next.
            rows = list(csv.DictReader(handle))[::every_nth]
        index = {name: i for i, name in enumerate(class_order)}
        unknown = {row["label"] for row in rows} - set(index)
        if not rows or unknown:
            raise ValueError(f"{manifest} is empty or has labels outside class_order: {sorted(unknown)}")
        self.images_dir = data_dir / "images"
        self.paths = [row["path"] for row in rows]
        self.labels = np.array([index[row["label"]] for row in rows], dtype=np.int64)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, i: int) -> tuple[torch.Tensor, int]:
        with Image.open(self.images_dir / self.paths[i]) as image:
            return self.transform(image.convert("L")), int(self.labels[i])


def build_train_transform(params: dict[str, Any]) -> transforms.Compose:
    """Strong augmentation used for the baseline (CLAHE and gamma were off)."""
    size = int(params["data"]["image_size"])
    aug = params["augmentation"]
    brightness, contrast, saturation = aug["color_jitter"]
    return transforms.Compose([
        transforms.Grayscale(num_output_channels=3),
        transforms.Resize((size, size)),
        transforms.RandomHorizontalFlip(p=aug["hflip_p"]),
        transforms.RandomAffine(degrees=aug["affine_degrees"],
                                translate=(aug["affine_translate"], aug["affine_translate"]),
                                scale=tuple(aug["affine_scale"])),
        transforms.ColorJitter(brightness=brightness, contrast=contrast, saturation=saturation),
        # Softer images, like a live webcam (blur strengthened after E-25 feedback).
        transforms.RandomApply([transforms.GaussianBlur(kernel_size=3, sigma=tuple(aug["blur_sigma"]))],
                               p=aug["blur_p"]),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        transforms.RandomErasing(p=aug["erasing_p"], scale=(0.02, 0.15), ratio=(0.3, 3.3), value=0),
    ])


def build_eval_transform(params: dict[str, Any]) -> transforms.Compose:
    """No augmentation: the same input contract cv-service and cv-eval use."""
    size = int(params["data"]["image_size"])
    return transforms.Compose([
        transforms.Grayscale(num_output_channels=3),
        transforms.Resize((size, size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def build_weighted_sampler(labels: np.ndarray, num_classes: int, strength: float,
                           generator: torch.Generator | None = None) -> WeightedRandomSampler:
    """strength 0 = uniform, 0.5 = sqrt rebalancing, 1 = fully balanced classes."""
    counts = np.bincount(labels, minlength=num_classes).astype(np.float64)
    counts = np.where(counts == 0, 1.0, counts)
    sample_weights = ((1.0 / counts) ** strength)[labels]
    return WeightedRandomSampler(torch.as_tensor(sample_weights, dtype=torch.double),
                                 num_samples=len(labels), replacement=True, generator=generator)


def build_mixed_sampler(label_sets: Sequence[np.ndarray], shares: Sequence[float], num_classes: int,
                        strength: float, generator: torch.Generator | None = None) -> WeightedRandomSampler:
    """Several datasets in one epoch: each source gets its share of the draws, and inside a
    source the classes are rebalanced exactly as build_weighted_sampler does."""
    weights = []
    for labels, share in zip(label_sets, shares, strict=True):
        counts = np.bincount(labels, minlength=num_classes).astype(np.float64)
        counts = np.where(counts == 0, 1.0, counts)
        per_sample = ((1.0 / counts) ** strength)[labels]
        weights.append(share * per_sample / per_sample.sum())
    return WeightedRandomSampler(torch.as_tensor(np.concatenate(weights), dtype=torch.double),
                                 num_samples=sum(len(labels) for labels in label_sets),
                                 replacement=True, generator=generator)


def compute_class_weights(labels: np.ndarray, num_classes: int, scheme: str = "sqrt",
                          beta: float = 0.9999) -> torch.Tensor:
    """Per-class loss weights, normalised to mean 1. Schemes: inverse | sqrt | effective | none."""
    counts = np.bincount(labels, minlength=num_classes).astype(np.float64)
    counts = np.where(counts == 0, 1.0, counts)
    if scheme == "inverse":
        weights = 1.0 / counts
    elif scheme == "sqrt":
        weights = 1.0 / np.sqrt(counts)
    elif scheme == "effective":
        weights = (1.0 - beta) / (1.0 - np.power(beta, counts))
    elif scheme == "none":
        weights = np.ones_like(counts)
    else:
        raise ValueError(f"unknown class-weight scheme: {scheme}")
    return torch.tensor(weights / weights.mean(), dtype=torch.float)


class MixupCutmixCollator:
    """Batch-level Mixup or CutMix. Returns (images, soft labels) for the focal loss."""

    def __init__(self, num_classes: int, prob: float, mixup_ratio: float, mixup_alpha: float,
                 cutmix_alpha: float, seed: int) -> None:
        self.num_classes = num_classes
        self.prob = prob
        self.mixup_ratio = mixup_ratio
        self.mixup_alpha = mixup_alpha
        self.cutmix_alpha = cutmix_alpha
        self.rng = np.random.default_rng(seed)

    def __call__(self, batch: list[tuple[torch.Tensor, int]]) -> tuple[torch.Tensor, torch.Tensor]:
        images = torch.stack([image for image, _ in batch])
        soft = F.one_hot(torch.tensor([label for _, label in batch]), self.num_classes).float()
        if self.rng.random() > self.prob:
            return images, soft
        perm = torch.from_numpy(self.rng.permutation(images.size(0)))
        if self.rng.random() < self.mixup_ratio:
            lam = float(self.rng.beta(self.mixup_alpha, self.mixup_alpha))
            return lam * images + (1 - lam) * images[perm], lam * soft + (1 - lam) * soft[perm]
        lam = float(self.rng.beta(self.cutmix_alpha, self.cutmix_alpha))
        _, _, h, w = images.shape
        cut = math.sqrt(1.0 - lam)
        cx, cy = int(self.rng.integers(w)), int(self.rng.integers(h))
        x1, x2 = max(cx - int(w * cut) // 2, 0), min(cx + int(w * cut) // 2, w)
        y1, y2 = max(cy - int(h * cut) // 2, 0), min(cy + int(h * cut) // 2, h)
        images[:, :, y1:y2, x1:x2] = images[perm, :, y1:y2, x1:x2]
        kept = 1.0 - (x2 - x1) * (y2 - y1) / (w * h)
        return images, kept * soft + (1 - kept) * soft[perm]
