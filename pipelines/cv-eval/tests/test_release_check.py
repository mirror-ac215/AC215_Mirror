from __future__ import annotations

import json

import pytest
import torch
from PIL import Image

from mirror_cv_eval import cli, release_check


class MeanPixel(torch.nn.Module):
    """Black photo -> 'a', white photo -> 'b': a model that gets both right."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        m = x.mean(dim=(1, 2, 3))
        return torch.stack([1 - m, m], dim=1)


class AlwaysA(torch.nn.Module):
    """Says 'a' for every photo: macro-F1 (2/3 + 0) / 2 = 0.33."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.tensor([[1.0, 0.0]]).repeat(len(x), 1)


@pytest.fixture
def ferplus(tmp_path, monkeypatch):
    data = tmp_path / "ferplus"
    (data / "metadata").mkdir(parents=True)
    (data / "manifests").mkdir()
    (data / "images").mkdir()
    spec = {
        "checkpoint": "gs://example/model.pth",
        "class_order": ["a", "b"],
        "inference_transform": {
            "grayscale_to_channels": 3,
            "resize": [2, 2],
            "pixel_range": [0.0, 1.0],
            "mean": [0.0] * 3,
            "std": [1.0] * 3,
        },
    }
    (data / "metadata" / "transform_spec.json").write_text(json.dumps(spec))
    Image.new("L", (2, 2), color=0).save(data / "images" / "black.png")
    Image.new("L", (2, 2), color=255).save(data / "images" / "white.png")
    manifest = data / "manifests" / "test.csv"
    manifest.write_text("path,label,split\nblack.png,a,test\nwhite.png,b,test\n")
    monkeypatch.setattr(release_check, "TEST_MANIFEST_SHA256", release_check.sha256_of(manifest))
    checkpoint = tmp_path / "model.pth"
    checkpoint.write_bytes(b"weights")
    return data, checkpoint, tmp_path / "report.json"


def check(data, checkpoint, output) -> int:
    return release_check.main(
        [
            "--data-dir",
            str(data),
            "--checkpoint",
            str(checkpoint),
            "--output",
            str(output),
            "--code-revision",
            "abc",
            "--model-version",
            "cv-test",
            "--device",
            "cpu",
        ]
    )


def test_a_model_above_the_guard_passes(ferplus, monkeypatch) -> None:
    data, checkpoint, output = ferplus
    monkeypatch.setattr(cli, "load_model", lambda path: MeanPixel())

    assert check(data, checkpoint, output) == 0
    report = json.loads(output.read_text())
    assert report["regression_guard"]["macro_f1_threshold"] == 0.609
    assert report["identity"]["dataset_version"] == "ferplus/v2"
    assert report["release_check"]["checkpoint_sha256"] == release_check.sha256_of(checkpoint)
    assert report["identity"]["model_uri"] == f"local:{checkpoint.name}"


def test_a_model_below_the_guard_fails(ferplus, monkeypatch) -> None:
    data, checkpoint, output = ferplus
    monkeypatch.setattr(cli, "load_model", lambda path: AlwaysA())

    assert check(data, checkpoint, output) == 2
    assert json.loads(output.read_text())["release_check"]["passed"] is False


def test_other_data_is_refused(ferplus, monkeypatch) -> None:
    data, checkpoint, output = ferplus
    monkeypatch.setattr(release_check, "TEST_MANIFEST_SHA256", "0" * 64)

    with pytest.raises(SystemExit, match="not the ferplus/v2 test manifest"):
        check(data, checkpoint, output)


def test_the_guard_cannot_be_loosened() -> None:
    with pytest.raises(SystemExit):
        release_check.parser().parse_args(
            ["--checkpoint", "c", "--output", "o", "--code-revision", "x", "--report-only"]
        )
    with pytest.raises(SystemExit):
        release_check.parser().parse_args(
            ["--checkpoint", "c", "--output", "o", "--code-revision", "x", "--threshold", "0.5"]
        )
