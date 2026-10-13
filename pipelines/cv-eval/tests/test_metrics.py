from __future__ import annotations

from mirror_cv_eval.metrics import evaluate_predictions, regression_passed


def test_evaluate_predictions_reports_expected_aggregate_metrics() -> None:
    result = evaluate_predictions(
        labels=("angry", "happy", "sad"),
        y_true=("angry", "happy", "sad", "sad"),
        y_pred=("angry", "sad", "sad", "happy"),
        top2=(("angry", "happy"), ("sad", "happy"), ("sad", "angry"), ("happy", "sad")),
    )

    assert result.n_examples == 4
    assert result.accuracy == 0.5
    assert result.top2_accuracy == 1.0
    assert result.confusion_matrix == ((1, 0, 0), (0, 0, 1), (0, 1, 1))
    assert result.per_class_f1 == {"angry": 1.0, "happy": 0.0, "sad": 0.5}
    assert result.macro_f1 == 0.5


def test_regression_guard_includes_the_threshold_boundary() -> None:
    assert regression_passed(0.64, threshold=0.64)
    assert not regression_passed(0.639999, threshold=0.64)
