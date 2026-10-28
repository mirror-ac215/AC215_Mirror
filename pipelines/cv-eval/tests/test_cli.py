from __future__ import annotations

import torch
from PIL import Image

from mirror_cv_eval import cli
from mirror_cv_eval.cli import parser


def test_parser_accepts_an_explicit_wandb_project() -> None:
    args = parser().parse_args(
        [
            "--data-dir",
            "data",
            "--checkpoint",
            "checkpoint.pth",
            "--output",
            "report.json",
            "--code-revision",
            "abc123",
            "--wandb-project",
            "mirror",
        ]
    )

    assert args.wandb_project == "mirror"


def test_transform_is_built_from_the_recorded_metadata() -> None:
    transform = cli.transform_from_metadata(
        {
            "grayscale_to_channels": 3,
            "resize": [2, 3],
            "pixel_range": [0.0, 1.0],
            "mean": [0.0, 0.0, 0.0],
            "std": [1.0, 1.0, 1.0],
        }
    )

    output = transform(Image.new("L", (1, 1), color=255).convert("RGB"))

    assert tuple(output.shape) == (3, 2, 3)
    assert output.tolist() == [[[1.0] * 3] * 2] * 3


def test_load_model_accepts_a_wrapped_state_dict(tmp_path) -> None:
    expected = torch.nn.Linear(2, 2)
    checkpoint = tmp_path / "checkpoint.pth"
    torch.save({"state_dict": expected.state_dict()}, checkpoint)

    loaded = cli.load_model(checkpoint, model_factory=lambda: torch.nn.Linear(2, 2))

    assert loaded.training is False
    assert loaded.state_dict().keys() == expected.state_dict().keys()
    for key, value in expected.state_dict().items():
        assert torch.equal(loaded.state_dict()[key], value)


def test_parser_defaults_keep_the_fer2013_guard() -> None:
    args = parser().parse_args(
        ["--data-dir", "data", "--checkpoint", "c.pth", "--output", "r.json", "--code-revision", "abc"]
    )

    assert args.dataset_version == "fer2013/v1"
    assert args.threshold == 0.64
    assert args.report_only is False
    assert args.device == "auto"
    assert args.model_version is None  # read from the checkpoint (Julie, #57)
    assert args.model_uri is None


def test_auto_device_uses_the_gpu_only_when_available(monkeypatch) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert cli.pick_device("auto").type == "cpu"

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    assert cli.pick_device("auto").type == "cuda"
    assert cli.pick_device("cpu").type == "cpu"

def test_model_version_comes_from_the_checkpoint(tmp_path) -> None:
    # Julie (#57): forgetting --model-version must not label a v4 report as v3.
    weights = torch.nn.Linear(2, 2).state_dict()
    for stored, expected in [("cv-vit-b16-v4", "cv-vit-b16-v4"), ("ViT_B_16_v3_focal_mixup", "cv-vit-b16-v3")]:
        checkpoint = tmp_path / f"{stored}.pth"
        torch.save({"model_name": stored, "model_state_dict": weights}, checkpoint)
        assert cli.model_version_from(checkpoint) == expected


def test_an_unknown_or_missing_model_name_asks_for_the_flag(tmp_path) -> None:
    import pytest

    for content in ({"model_name": "my_experiment"}, {"state_dict": {}}):
        checkpoint = tmp_path / "c.pth"
        torch.save(content, checkpoint)
        with pytest.raises(SystemExit, match="pass --model-version"):
            cli.model_version_from(checkpoint)
