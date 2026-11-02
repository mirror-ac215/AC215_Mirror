from __future__ import annotations

from pydantic import Field, model_validator
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
    # Pinned to an immutable Hugging Face commit: a rebuild always loads the same weights.
    # Change it only on purpose (see "Model pin" in README.md), never back to "main".
    text_emotion_model: str = "j-hartmann/emotion-english-distilroberta-base"
    text_emotion_revision: str = "0e1cd914e3d46199ed785853e12b57304e04178b"
    # Longer messages are cut before scoring (the API allows up to 4000 characters).
    text_emotion_max_chars: int = 2000

    # Smoothing and gating of the camera signal (M3-04). Each cv-service frame
    # result is noisy, so the gateway averages the recent ones and decides
    # whether the reading is steady enough to use.
    # Provisional (experimental) thresholds: chosen with a sweep on held-out Aff-Wild2 video
    # (scripts/gate_sweep.py, see the README) using cv-vit-b16-v4, which is not the served
    # model yet. Re-run the sweep when the served model changes or our own labelled sessions
    # (M3-20) are ready. Out-of-range values are rejected at startup.
    # allow_inf_nan=False: an infinite window would keep stale frames forever.
    gate_window_s: float = Field(default=10.0, gt=0, allow_inf_nan=False)  # only frames from the last N seconds count
    gate_min_frames: int = Field(default=3, ge=1)  # fewer frames with a face -> "dropped"
    gate_min_face_ratio: float = Field(default=0.5, ge=0, le=1)  # face in under half -> "dropped"
    gate_min_top_prob: float = Field(default=0.45, ge=0, le=1)  # averaged top emotion must reach this
    gate_min_margin: float = Field(default=0.05, ge=0, le=1)  # ...and lead the second by this much
    gate_min_stability: float = Field(default=0.50, ge=0, le=1)  # ...and be top in this share of frames
    gate_max_frames: int = Field(default=30, ge=1)  # cap per session (about 30-60 s of frames)

    @model_validator(mode="after")
    def _window_can_hold_enough_frames(self) -> Settings:
        # A window smaller than the minimum would report "dropped" forever.
        if self.gate_max_frames < self.gate_min_frames:
            raise ValueError("gate_max_frames must be at least gate_min_frames")
        return self
