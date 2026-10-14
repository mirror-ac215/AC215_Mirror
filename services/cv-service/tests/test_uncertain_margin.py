from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.runtime import ModelSettings


def test_uncertain_margin_defaults_to_current_deployed_value() -> None:
    settings = ModelSettings(_env_file=None)

    assert settings.uncertain_margin == 0.1


def test_uncertain_margin_accepts_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNCERTAIN_MARGIN", "0.25")

    settings = ModelSettings(_env_file=None)

    assert settings.uncertain_margin == 0.25


def test_uncertain_margin_rejects_values_outside_probability_range() -> None:
    with pytest.raises(ValidationError):
        ModelSettings(_env_file=None, uncertain_margin=1.01)
