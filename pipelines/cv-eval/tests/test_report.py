from __future__ import annotations

from mirror_cv_eval.metrics import EvaluationMetrics
from mirror_cv_eval.report import build_report


def test_build_report_records_evaluation_identity_and_regression_result() -> None:
    report = build_report(
        model_uri="gs://mirror-ac215-data/models/cv/inherited-v3/vit_b16_v3_best.pth",
        model_version="cv-vit-b16-v3",
        dataset_version="fer2013/v1",
        code_revision="2dff08e",
        class_order=("angry", "happy"),
        transform={"resize": [224, 224]},
        threshold=0.64,
        metrics=EvaluationMetrics(
            n_examples=10,
            accuracy=0.7,
            top2_accuracy=0.9,
            macro_f1=0.64,
            per_class_f1={"angry": 0.6, "happy": 0.68},
            confusion_matrix=((3, 2), (1, 4)),
        ),
    )

    assert report["identity"]["model_uri"].endswith("vit_b16_v3_best.pth")
    assert report["identity"]["code_revision"] == "2dff08e"
    assert report["regression_guard"] == {"macro_f1_threshold": 0.64, "passed": True}
    assert report["metrics"]["confusion_matrix"] == [[3, 2], [1, 4]]
