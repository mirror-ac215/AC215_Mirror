from app import runtime


def test_load_runtime_reports_the_configured_paired_model_version(
    monkeypatch,
) -> None:
    settings = runtime.ModelSettings(
        model_object="models/cv/approved/vit_b16_v4.pth",
        model_version="cv-vit-b16-v4",
    )
    detector = object()
    classifier = object()
    model = object()

    monkeypatch.setattr(runtime, "FaceDetector", lambda: detector)
    monkeypatch.setattr(runtime, "load_model", lambda *_args, **_kwargs: model)
    monkeypatch.setattr(runtime, "ExpressionClassifier", lambda value: classifier)

    loaded_detector, loaded_classifier, version = runtime.load_runtime(settings)

    assert loaded_detector is detector
    assert loaded_classifier is classifier
    assert version == "cv-vit-b16-v4"
