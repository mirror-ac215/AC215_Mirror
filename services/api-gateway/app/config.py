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

    # Smoothing and gating of the camera signal (M3-04). Each cv-service frame
    # result is noisy, so the gateway averages the recent ones and decides
    # whether the reading is steady enough to use. The three "ok" thresholds were chosen with
    # a sweep on held-out Aff-Wild2 video (scripts/gate_sweep.py, see the README): "ok" in about
    # 31 % of 10-second windows and right 64 % of the time (current CV model, cv-vit-b16-v4).
    gate_window_s: float = 10.0  # only frames from the last N seconds count
    gate_min_frames: int = 3  # fewer frames with a face than this -> "dropped"
    gate_min_face_ratio: float = 0.5  # face found in under half the frames -> "dropped"
    gate_min_top_prob: float = 0.45  # averaged top emotion must reach this for "ok"
    gate_min_margin: float = 0.05  # ...and lead the second emotion by this much
    gate_min_stability: float = 0.50  # ...and be the top emotion in this share of frames
    gate_max_frames: int = 30  # cap per session so memory stays small (about 30-60 s of frames)
