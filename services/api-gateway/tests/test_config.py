from app.config import Settings


def test_settings_have_safe_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "mirror-api-gateway"


def test_llm_model_and_timeout_are_independently_configurable(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "mirror-persona-v1")
    monkeypatch.setenv("LLM_TIMEOUT_S", "9.5")

    settings = Settings()

    assert settings.llm_model == "mirror-persona-v1"
    assert settings.llm_timeout_s == 9.5
