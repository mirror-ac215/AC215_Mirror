from pathlib import Path

from app.runtime import ModelSettings

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def test_documented_serving_configuration_has_no_independent_version_tag() -> None:
    """Version attribution must come only from the reviewed MODEL_VERSION setting."""
    example = (SERVICE_ROOT / ".env.example").read_text()

    assert "MODEL_VERSION_TAG_OBJECT" not in example
    assert "model_version_tag_object" not in ModelSettings.model_fields


def test_documented_default_object_and_version_are_present() -> None:
    settings = ModelSettings()

    assert settings.model_object == "models/cv/inherited-v3/vit_b16_v3_best.pth"
    assert settings.model_version == "cv-vit-b16-v3"
