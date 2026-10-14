from __future__ import annotations

from types import SimpleNamespace

from mirror_cv_eval.tracking import log_aggregate_report


def test_log_aggregate_report_sends_identity_guard_and_aggregate_metrics_only() -> None:
    init_calls: list[dict[str, object]] = []
    logged: list[dict[str, object]] = []
    finished: list[bool] = []

    def init(**kwargs: object) -> SimpleNamespace:
        init_calls.append(kwargs)
        return SimpleNamespace(
            log=lambda payload: logged.append(payload),
            finish=lambda: finished.append(True),
        )

    fake_wandb = SimpleNamespace(init=init)
    report = {
        "identity": {"model_version": "cv-vit-b16-v3", "dataset_version": "fer2013/v1"},
        "regression_guard": {"macro_f1_threshold": 0.64, "passed": True},
        "metrics": {"n_examples": 10, "accuracy": 0.7, "macro_f1": 0.64},
        "runtime": {"seconds": 1.2, "batch_size": 32},
    }

    log_aggregate_report(report, project="mirror", wandb_module=fake_wandb)

    assert init_calls == [
        {
            "project": "mirror",
            "job_type": "cv-evaluation",
            "config": {
                "model_version": "cv-vit-b16-v3",
                "dataset_version": "fer2013/v1",
                "macro_f1_threshold": 0.64,
            },
        }
    ]
    assert logged == [
        {
            "metrics/n_examples": 10,
            "metrics/accuracy": 0.7,
            "metrics/macro_f1": 0.64,
            "runtime/seconds": 1.2,
            "runtime/batch_size": 32,
            "regression_guard/passed": True,
        }
    ]
    assert finished == [True]
