"""Requests and response shapes from docs/contracts/api-gateway.openapi.yaml."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

Role = Literal["patient", "clinician"]
VisualStatus = Literal["ok", "uncertain", "dropped", "camera_off"]


class LoginRequest(BaseModel):
    # Simple shape check (something@something.something), so a malformed email gets 422.
    # Not pydantic's EmailStr: it rejects the reserved .test domain our demo users use.
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str


class LoginResponse(BaseModel):
    access_token: str
    role: Role
    user_id: str


class SessionCreate(BaseModel):
    camera_consent: bool


class Session(BaseModel):
    session_id: str
    started_at: datetime
    camera_consent: bool


class PatientSummary(BaseModel):
    """One clinician-owned patient with no raw messages or frames."""

    patient_id: str
    display_name: str
    last_session_at: datetime | None
    needs_review: bool


VisualEmotionLabel = Literal[
    "angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"
]
TrendEmotionLabel = Literal[
    "anger",
    "angry",
    "disgust",
    "fear",
    "happy",
    "joy",
    "neutral",
    "sad",
    "sadness",
    "surprise",
]
VisualLabelProbability = tuple[
    VisualEmotionLabel,
    Annotated[float, Field(ge=0, le=1)],
]
TrendLabelProbability = tuple[
    TrendEmotionLabel,
    Annotated[float, Field(ge=0, le=1)],
]


class TrendPoint(BaseModel):
    """One stored aggregate emotion window for a clinician-owned patient."""

    ts: datetime
    visual_status: VisualStatus
    visual_top2: Annotated[list[TrendLabelProbability] | None, Field(max_length=2)] = None
    text_top2: Annotated[list[TrendLabelProbability] | None, Field(max_length=2)] = None
    tone_mode: Literal["coach", "supportive"]


class ReviewFlagUpdate(BaseModel):
    """The API permits only marking an unresolved review flag complete."""

    reviewed: Literal[True]


class ReviewFlagSummary(BaseModel):
    """Clinician-visible flag metadata, deliberately excluding message content."""

    flag_id: UUID
    created_at: datetime
    reviewed_at: datetime | None


class ReviewFlagAcknowledgement(BaseModel):
    """Confirmation that one review flag transitioned to reviewed."""

    reviewed: Literal[True]


class FrameAck(BaseModel):
    visual_status: VisualStatus
    # Smoothed over the gate window, never one frame. Only present when the status is "ok".
    top2: Annotated[list[VisualLabelProbability] | None, Field(max_length=2)] = None


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
