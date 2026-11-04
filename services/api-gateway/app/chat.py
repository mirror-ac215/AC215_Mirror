"""Login, sessions, camera readings, and safety-first chat turns."""

import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app import metrics
from app.auth import DemoUser, demo_login, require_patient
from app.clients import CVClient, LLMServiceClient
from app.config import Settings
from app.fusion import TurnHistory
from app.gating import FrameReading, FrameWindow, gate
from app.orchestration import ChatOrchestrator
from app.repository import PostgresRepository
from app.schemas import (
    FrameAck,
    LoginRequest,
    LoginResponse,
    MessageRequest,
    Session,
    SessionCreate,
)
from app.text_emotion import get_text_emotion

router = APIRouter()
settings = Settings()
sessions: dict[str, Session] = {}
session_owners: dict[str, str] = {}
frame_windows: dict[str, FrameWindow] = {}
turn_histories: dict[str, TurnHistory] = {}
conversations: dict[str, list[dict[str, str]]] = {}
repository = PostgresRepository.from_dsn(settings.database_url)
llm_client = LLMServiceClient(
    settings.llm_service_url, settings.llm_timeout_s, settings.llm_model
)
cv_client = CVClient(settings.cv_service_url, settings.dependency_timeout_s)
logger = logging.getLogger("mirror")
# Compatibility-only audit view; the durable source of review flags is Postgres.
review_flags: list[dict] = []


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def get_owned_session(session_id: str, user: DemoUser) -> Session:
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    if session_owners[session_id] != user.user_id:
        raise HTTPException(status_code=403, detail="Not your session")
    return session


def visual_context(session_id: str, session: Session) -> dict:
    return gate(
        frame_windows[session_id].recent(time.monotonic(), settings.gate_window_s),
        settings,
        session.camera_consent,
    )


@router.post("/auth/login", responses={401: {"description": "Not logged in"}})
def login(body: LoginRequest) -> LoginResponse:
    return demo_login(body.email, body.password)


@router.post(
    "/sessions",
    status_code=201,
    responses={
        401: {"description": "Not logged in"},
        403: {"description": "Patients only"},
    },
)
async def start_session(
    body: SessionCreate, user: Annotated[DemoUser, Depends(require_patient)]
) -> Session:
    session = Session(
        session_id=str(uuid4()),
        started_at=datetime.now(UTC),
        camera_consent=body.camera_consent,
    )
    try:
        await repository.add_session(
            session.session_id, user.user_id, session.started_at, session.camera_consent
        )
    except Exception as exc:
        logger.error("session_persistence_failed type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503, detail="Session is temporarily unavailable"
        ) from exc
    sessions[session.session_id] = session
    session_owners[session.session_id] = user.user_id
    frame_windows[session.session_id] = FrameWindow(settings.gate_max_frames)
    turn_histories[session.session_id] = TurnHistory()
    conversations[session.session_id] = []
    return session


@router.post(
    "/sessions/{session_id}/frames",
    status_code=202,
    responses={
        401: {"description": "Not logged in"},
        403: {"description": "Not a patient, or not this patient's session"},
        404: {"description": "Unknown session"},
        409: {"description": "Camera consent not given"},
        413: {"description": "Frame too large"},
        415: {"description": "Unsupported Media Type"},
        503: {"description": "Camera analysis is temporarily unavailable"},
    },
)
async def receive_frame(
    session_id: str,
    image: UploadFile,
    user: Annotated[DemoUser, Depends(require_patient)],
) -> FrameAck:
    session = get_owned_session(session_id, user)
    if not session.camera_consent:
        raise HTTPException(status_code=409, detail="Camera consent was not given")
    if image.content_type != "image/jpeg":
        raise HTTPException(status_code=415, detail="Frame must be JPEG")
    data = await image.read(settings.max_frame_bytes + 1)
    if len(data) > settings.max_frame_bytes:
        raise HTTPException(status_code=413, detail="Frame too large")
    try:
        prediction = await cv_client.predict(data)
    except Exception as exc:
        logger.warning("cv_prediction_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=503, detail="Camera analysis is unavailable"
        ) from exc
    frame_windows[session_id].add(
        FrameReading.from_cv_payload(prediction, time.monotonic())
    )
    # Return the current gate result, not an optimistic usable-reading claim.
    return FrameAck(visual_status=visual_context(session_id, session)["status"])


@router.post(
    "/sessions/{session_id}/messages",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-sent Events",
            "content": {"text/event-stream": {}},
        },
        401: {"description": "Not logged in"},
        403: {"description": "Not a patient, or not this patient's session"},
        404: {"description": "Unknown session"},
    },
)
async def send_message(
    session_id: str,
    body: MessageRequest,
    user: Annotated[DemoUser, Depends(require_patient)],
) -> StreamingResponse:
    session = get_owned_session(session_id, user)
    orchestrator = ChatOrchestrator(repository, llm_client, get_text_emotion())
    try:
        turn = await orchestrator.start_turn(
            session_id=session_id,
            patient_id=user.user_id,
            text=body.text,
            visual=visual_context(session_id, session),
            history=turn_histories[session_id],
            conversation=conversations[session_id],
        )
    except Exception as exc:
        logger.error("chat_persistence_orchestration_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=503, detail="Chat is temporarily unavailable"
        ) from exc

    if turn.crisis is not None:
        rule = turn.safety_rule or "unknown"
        logger.info("safety_hit kind=crisis rule=%s", rule)
        metrics.CRISIS_HITS.labels(rule=rule).inc()
        review_flags.append(
            {
                "patient_id": user.user_id,
                "session_id": session_id,
                "message_id": turn.message_id,
                "rule_id": rule,
                "urgency": "urgent",
            }
        )
        return StreamingResponse(
            iter([sse("crisis", turn.crisis)]), media_type="text/event-stream"
        )

    async def events() -> AsyncIterator[str]:
        reply_parts: list[str] = []
        async for token in turn.tokens:
            reply_parts.append(token)
            yield sse("token", {"text": token})
        conversations[session_id].extend(
            (
                {"role": "user", "content": body.text},
                {"role": "assistant", "content": "".join(reply_parts)},
            )
        )
        yield sse("done", {"message_id": turn.message_id, "context": turn.context})

    return StreamingResponse(events(), media_type="text/event-stream")
