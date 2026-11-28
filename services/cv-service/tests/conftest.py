"""Shared test setup: the YuNet model file is downloaded (sha256-checked) if missing."""

import pytest

from app.fetch_models import ensure_yunet


@pytest.fixture(scope="session", autouse=True)
def yunet_model_file() -> None:
    ensure_yunet()
