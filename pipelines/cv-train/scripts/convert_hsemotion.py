"""Rebuild HSEmotion enet_b2_7 as a timm tf_efficientnet_b2 checkpoint that cv-train can start from.

HSEmotion (https://github.com/av-savchenko/hsemotion, Apache-2.0 code; weights trained on AffectNet,
research use only) publishes its PyTorch weights as a pickled model, which would run code on load.
This script uses its ONNX release instead, so nothing is unpickled:

1. copy every convolution's weights from the ONNX file into a fresh timm tf_efficientnet_b2
   (global max pooling, 7 classes) in forward order;
2. ONNX folded each BatchNorm into its convolution (W, b), so the BatchNorm is rebuilt with running
   statistics measured on real faces and gamma = sqrt(var + eps), beta = mean + b: the eval output
   stays exactly W x + b, and fine-tuning starts from realistic statistics;
3. prove it: both versions must give the same answer on 200 real faces (max logit difference < 1e-3).

Usage (from the repository root; downloads the 31 MB ONNX file once):
    uv run --no-sync --project pipelines/cv-train --with onnx --with onnxruntime \\
        python pipelines/cv-train/scripts/convert_hsemotion.py \\
        data/processed/affwild2/v1 data/models/hsemotion_b2_7_init.pth
"""

from __future__ import annotations

import csv
import sys
import urllib.request
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import timm
import torch
from onnx import numpy_helper
from PIL import Image

ONNX_URL = ("https://github.com/HSE-asavchenko/face-emotion-recognition/blob/main/"
            "models/affectnet_emotions/onnx/enet_b2_7.onnx?raw=true")
MEAN, STD = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])


def onnx_file() -> Path:
    path = Path.home() / ".hsemotion" / "enet_b2_7.onnx"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(ONNX_URL, path)
    return path


def faces(data_dir: Path, count: int = 1500) -> np.ndarray:
    """Grey, 260 px, ImageNet-normalised training frames: the same input cv-train uses."""
    rows = list(csv.DictReader((data_dir / "manifests" / "train.csv").open(encoding="utf-8")))[::50][:count]
    images = []
    for row in rows:
        image = Image.open(data_dir / "images" / row["path"]).convert("L").convert("RGB")
        pixels = np.asarray(image.resize((260, 260), Image.BILINEAR)) / 255.0
        images.append(((pixels - MEAN) / STD).transpose(2, 0, 1).astype(np.float32))
    return np.stack(images)


def conv_bn_pairs(model: torch.nn.Module) -> list[tuple[torch.nn.Conv2d, torch.nn.BatchNorm2d | None]]:
    """Every convolution in forward order, with the BatchNorm that follows it (None for SE convs)."""
    pairs, pending = [], None
    for module in model.modules():
        if isinstance(module, torch.nn.Conv2d):
            if pending is not None:
                pairs.append((pending, None))
            pending = module
        elif isinstance(module, torch.nn.BatchNorm2d):
            pairs.append((pending, module))
            pending = None
    if pending is not None:
        pairs.append((pending, None))
    return pairs


def convert(data_dir: Path, output: Path) -> None:
    source = onnx_file()
    graph = onnx.load(source).graph
    weights = {tensor.name: numpy_helper.to_array(tensor) for tensor in graph.initializer}
    onnx_convs = [node for node in graph.node if node.op_type == "Conv"]
    model = timm.create_model("tf_efficientnet_b2", num_classes=7, pretrained=False, global_pool="max").eval()
    pairs = conv_bn_pairs(model)
    if len(pairs) != len(onnx_convs):
        raise ValueError(f"{len(pairs)} timm convolutions vs {len(onnx_convs)} in the ONNX graph")

    for (conv, bn), node in zip(pairs, onnx_convs, strict=True):
        weight, bias = weights[node.input[1]], weights[node.input[2]]
        if tuple(conv.weight.shape) != weight.shape:
            raise ValueError(f"shape mismatch: {tuple(conv.weight.shape)} vs {weight.shape}")
        conv.weight.data = torch.from_numpy(weight.copy())
        if bn is None:
            conv.bias.data = torch.from_numpy(bias.copy())
        else:  # identity BatchNorm carrying the folded bias, calibrated below
            bn.running_mean.zero_()
            bn.running_var.fill_(1 - bn.eps)
            bn.weight.data.fill_(1.0)
            bn.bias.data = torch.from_numpy(bias.copy())
    gemm = next(node for node in graph.node if node.op_type == "Gemm")
    model.classifier.weight.data = torch.from_numpy(weights[gemm.input[1]].copy())
    model.classifier.bias.data = torch.from_numpy(weights[gemm.input[2]].copy())

    # Measure each convolution's output on real faces; set BatchNorm so eval output is unchanged.
    images = faces(data_dir)
    sums: dict[torch.nn.BatchNorm2d, list[torch.Tensor]] = {}
    hooks = []
    for conv, bn in pairs:
        if bn is not None:
            def record(module, inputs, output, bn=bn):
                y = output.detach().double()
                totals = sums.setdefault(bn, [torch.zeros(y.shape[1], dtype=torch.double)] * 2 + [0])
                totals[0] = totals[0] + y.sum((0, 2, 3))
                totals[1] = totals[1] + (y * y).sum((0, 2, 3))
                totals[2] += y.shape[0] * y.shape[2] * y.shape[3]
            hooks.append(conv.register_forward_hook(record))
    with torch.no_grad():
        for start in range(0, len(images), 100):
            model(torch.from_numpy(images[start:start + 100]))
    for hook in hooks:
        hook.remove()
    for bn, (total, total_sq, count) in sums.items():
        mean = total / count
        var = (total_sq / count - mean * mean).clamp_min(1e-6)
        folded_bias = bn.bias.data.double().clone()
        bn.running_mean.data = mean.float()
        bn.running_var.data = var.float()
        bn.weight.data = torch.sqrt(var + bn.eps).float()
        bn.bias.data = (mean + folded_bias).float()

    # Proof: the rebuilt model gives the ONNX model's answers.
    check = images[-200:]
    reference = ort.InferenceSession(str(source), providers=["CPUExecutionProvider"]).run(None, {"input": check})[0]
    with torch.no_grad():
        rebuilt = model(torch.from_numpy(check)).numpy()
    difference = float(np.abs(reference - rebuilt).max())
    same_top1 = float((reference.argmax(1) == rebuilt.argmax(1)).mean())
    print(f"max logit difference {difference:.2e}, same top-1 on {same_top1:.0%} of {len(check)} faces")
    if difference > 1e-3 or same_top1 < 1.0:
        raise SystemExit("conversion does not reproduce the ONNX model; nothing saved")

    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state_dict": model.state_dict(), "architecture": "tf_efficientnet_b2",
                "global_pool": "max", "source": "HSEmotion enet_b2_7 (AffectNet; research use only)"}, output)
    print(f"saved {output}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: convert_hsemotion.py <affwild2 data dir> <output .pth>")
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
