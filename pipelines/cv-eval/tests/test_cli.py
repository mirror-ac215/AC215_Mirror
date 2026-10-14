from __future__ import annotations

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
