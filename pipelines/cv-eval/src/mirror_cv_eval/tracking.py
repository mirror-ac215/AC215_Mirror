"""Optional aggregate-only Weights & Biases tracking for CV evaluation."""

from __future__ import annotations

from typing import Any, Protocol, cast


class WandbRun(Protocol):
    def log(self, payload: dict[str, object]) -> None: ...

    def finish(self) -> None: ...


class WandbModule(Protocol):
    def init(self, **kwargs: object) -> WandbRun: ...


def log_aggregate_report(
    report: dict[str, Any], *, project: str, wandb_module: WandbModule | None = None
) -> None:
    """Log only the local report's aggregate metrics and evaluation identity."""
    if wandb_module is None:
        import wandb

        wandb_module = cast(WandbModule, wandb)

    identity = report["identity"]
    guard = report["regression_guard"]
    metrics = report["metrics"]
    runtime = report["runtime"]
    run = wandb_module.init(
        project=project,
        job_type="cv-evaluation",
        config={
            "model_version": identity["model_version"],
            "dataset_version": identity["dataset_version"],
            "macro_f1_threshold": guard["macro_f1_threshold"],
        },
    )
    run.log(
        {
            "metrics/n_examples": metrics["n_examples"],
            "metrics/accuracy": metrics["accuracy"],
            "metrics/macro_f1": metrics["macro_f1"],
            "runtime/seconds": runtime["seconds"],
            "runtime/batch_size": runtime["batch_size"],
            "regression_guard/passed": guard["passed"],
        }
    )
    run.finish()
