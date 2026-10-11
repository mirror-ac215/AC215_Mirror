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
