"""Aggregate classification metrics with no raw-example persistence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationMetrics:
    """Aggregate metrics and derived confusion matrix for a fixed label order."""

    n_examples: int
    accuracy: float
    top2_accuracy: float
    macro_f1: float
    per_class_f1: dict[str, float]
    confusion_matrix: tuple[tuple[int, ...], ...]


def evaluate_predictions(
    *,
    labels: tuple[str, ...],
    y_true: tuple[str, ...],
    y_pred: tuple[str, ...],
    top2: tuple[tuple[str, ...], ...],
) -> EvaluationMetrics:
    """Calculate deterministic aggregate metrics for a fixed class order."""
    if not y_true or len(y_true) != len(y_pred) or len(y_true) != len(top2):
        raise ValueError("predictions, labels, and top2 values must be non-empty and aligned")
    label_indices = {label: index for index, label in enumerate(labels)}
    if len(label_indices) != len(labels):
        raise ValueError("labels must be unique")
    matrix = [[0 for _ in labels] for _ in labels]
    for actual, predicted in zip(y_true, y_pred, strict=True):
        if actual not in label_indices or predicted not in label_indices:
            raise ValueError("all predicted and actual labels must be declared")
        matrix[label_indices[actual]][label_indices[predicted]] += 1
    per_class_f1: dict[str, float] = {}
    for index, label in enumerate(labels):
        true_positive = matrix[index][index]
        false_positive = sum(matrix[row][index] for row in range(len(labels)) if row != index)
        false_negative = sum(matrix[index][column] for column in range(len(labels)) if column != index)
        denominator = 2 * true_positive + false_positive + false_negative
        per_class_f1[label] = 0.0 if denominator == 0 else 2 * true_positive / denominator
    correct = sum(matrix[index][index] for index in range(len(labels)))
    return EvaluationMetrics(
        n_examples=len(y_true),
        accuracy=correct / len(y_true),
        top2_accuracy=sum(actual in candidates for actual, candidates in zip(y_true, top2, strict=True)) / len(y_true),
        macro_f1=sum(per_class_f1.values()) / len(labels),
        per_class_f1=per_class_f1,
        confusion_matrix=tuple(tuple(row) for row in matrix),
    )


def regression_passed(macro_f1: float, *, threshold: float) -> bool:
    """Return whether macro-F1 meets the inclusive regression guard."""
    return macro_f1 >= threshold