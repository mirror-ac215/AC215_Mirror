from scripts.gate_sweep import sweep_settings


def test_gate_sweep_uses_scoped_non_secret_runtime_values() -> None:
    settings = sweep_settings()

    assert settings.database_url.startswith("postgresql://unused:")
    assert len(settings.jwt_signing_key) >= 32