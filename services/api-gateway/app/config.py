from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration supplied through environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "mirror-api-gateway"
    log_level: str = "INFO"

    # Where the other services live. The defaults are the docker-compose service
    # names: inside the compose network, containers find each other by name
    cv_service_url: str = "http://cv-service:8001"
    llm_service_url: str = "http://llm-service:8002"
    db_host: str = "db"
    db_port: int = 5432
    dependency_timeout_s: float = 2.0

    # Biggest camera frame we accept. The frontend sends small downscaled JPEGs
    # (tens of KB), so 1 MB is generous; anything larger is rejected with 413.
    max_frame_bytes: int = 1_000_000

    # Browser origins allowed to call the gateway (frontend dev server and container).
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Demo login password for all seeded users (same env var as services/db/seed.sh).
    # Local development only; M4-02 replaces this with real password hashes.
    mirror_demo_password: str = "mirror-demo"

    # Text-emotion module (M3-05). Model chosen in M2-11 (D-003 in docs/decisions.md).
    # Pinned to an immutable Hugging Face commit, so a rebuild always loads the same weights.
    # Change it only on purpose (see "Model pin" in README.md), never back to "main".
    text_emotion_model: str = "j-hartmann/emotion-english-distilroberta-base"
    text_emotion_revision: str = "0e1cd914e3d46199ed785853e12b57304e04178b"
    # Longer messages are cut before scoring (the API allows up to 4000 characters).
    text_emotion_max_chars: int = 2000
