"""Machine-readable, aggregate-only evaluation reports."""

from __future__ import annotations

from typing import Any

from mirror_cv_eval.metrics import EvaluationMetrics, regression_passed


def build_report(
    *,
    model_uri: str,
    model_version: str,
    dataset_version: str,
    code_revision: str,
    class_order: tuple[str, ...],
    transform: dict[str, Any],
    threshold: float,
    metrics: EvaluationMetrics,
) -> dict[str, Any]:
    """Create a serializable report without frames, predictions, or credentials."""
    return {
        "identity": {
            "model_uri": model_uri,
            "model_version": model_version,
            "dataset_version": dataset_version,
            "code_revision": code_revision,
            "class_order": list(class_order),
            "inference_transform": transform,
        },
        "regression_guard": {
            "macro_f1_threshold": threshold,
            "passed": regression_passed(metrics.macro_f1, threshold=threshold),
        },
        "metrics": {
            "n_examples": metrics.n_examples,
            "accuracy": metrics.accuracy,
            "top2_accuracy": metrics.top2_accuracy,
            "macro_f1": metrics.macro_f1,
            "per_class_f1": metrics.per_class_f1,
            "confusion_matrix": [list(row) for row in metrics.confusion_matrix],
        },
    }
