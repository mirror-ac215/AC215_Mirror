"""Login, sessions, frames and messages.

v0 stubs: the shapes follow the contract, the data is fake. The real CV call,
safety check, fusion and LLM call arrive in MS3.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app import safety
from app.auth import DemoUser, demo_login, require_patient
from app.config import Settings
from app.logging_config import request_id_context
from app.schemas import (
    FrameAck,
    LoginRequest,
    LoginResponse,
    MessageRequest,
    Session,
    SessionCreate,
)

# APIRouter groups related endpoints in their own file, which keeps main.py small. Main then plus in the router
router = APIRouter()

# Reads env vars (e.g. MAX_FRAME_BYTES), falling back to config.py defaults.
settings = Settings()

# In-memory store, lost on restart. The database replaces this later (M3-10).
sessions: dict[str, Session] = {}

# Who created each session: session_id -> user_id. Kept out of Session so the
# response shape still matches the contract.
session_owners: dict[str, str] = {}

# Review flags for the patient's clinician: "urgent" from the crisis rules,
# "routine" from the support rules.
# In memory for now; M3-10 writes them to the review_flags table instead
# (and sets messages.safety_hit).
review_flags: list[dict] = []

logger = logging.getLogger("mirror")

STUB_REPLY = "Thanks for telling me that. What feels most important to talk about right now?"


def sse(event: str, data: dict) -> str:
    """One Server-Sent Event: an event name, a JSON data line, then a blank line."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def get_owned_session(session_id: str, user: DemoUser) -> Session:
    """404 if the session doesn't exist; 403 if it belongs to another patient."""
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    if session_owners[session_id] != user.user_id:
        raise HTTPException(status_code=403, detail="Not your session")
    return session


@router.post(
    "/auth/login",
    responses={401: {"description": "Not logged in"}},
)
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
def start_session(
    body: SessionCreate, user: Annotated[DemoUser, Depends(require_patient)]
) -> Session:
    session = Session(
        session_id=str(uuid4()),
        started_at=datetime.now(UTC),
        camera_consent=body.camera_consent,
    )
    sessions[session.session_id] = session
    session_owners[session.session_id] = user.user_id
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
    },
)
async def receive_frame(
    session_id: str, image: UploadFile, user: Annotated[DemoUser, Depends(require_patient)]
) -> FrameAck:
    session = get_owned_session(session_id, user)
    if not session.camera_consent:
        raise HTTPException(status_code=409, detail="Camera consent was not given")

    # Guard 1: only JPEG frames
    if image.content_type != "image/jpeg":
        raise HTTPException(status_code=415, detail="Frame must be JPEG")

    # Guard 2: bounded read. Read at most one byte past the limit, so a huge
    # upload can't fill the gateway's memory. Frames are still never stored.
    data = await image.read(settings.max_frame_bytes + 1)
    if len(data) > settings.max_frame_bytes:
        raise HTTPException(status_code=413, detail="Frame too large")
    return FrameAck(visual_status="ok")


@router.post(
    "/sessions/{session_id}/messages",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-sent Events: [support], token events, done; or one crisis or medical event",
            "content": {"text/event-stream": {}},
        },
        401: {"description": "Not logged in"},
        403: {"description": "Not a patient, or not this patient's session"},
        404: {"description": "Unknown session"},
    },
)
def send_message(
    session_id: str, body: MessageRequest, user: Annotated[DemoUser, Depends(require_patient)]
) -> StreamingResponse:
    get_owned_session(session_id, user)
    message_id = str(uuid4())

    # Safety check first (M3-07), before text emotion, fusion or the LLM.
    result = safety.check(body.text)
    if result.hit:
        # Log the rule, never the text.
        logger.info("safety_hit kind=%s rule=%s", result.kind, result.rule_id)
    if result.kind in ("crisis", "support"):
        review_flags.append(
            {
                "patient_id": user.user_id,
                "session_id": session_id,
                "message_id": message_id,
                "rule_id": result.rule_id,
                "urgency": "urgent" if result.kind == "crisis" else "routine",
                "request_id": request_id_context.get(),
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
    if result.kind == "crisis":
        payload = safety.crisis_payload(review_flag_created=True)
        return StreamingResponse(
            iter([sse("crisis", payload)]), media_type="text/event-stream"
        )
    if result.kind == "medical":
        return StreamingResponse(
            iter([sse("medical", safety.medical_payload())]), media_type="text/event-stream"
        )

    async def events() -> AsyncIterator[str]:
        if result.kind == "support":
            # The in-between: offer a person first, then keep the conversation going.
            yield sse(
                "support",
                safety.support_payload(
                    settings.clinic_booking_url,
                    settings.clinic_phone,
                    settings.live_support_available,
                ),
            )
        for word in STUB_REPLY.split(" "):
            yield sse("token", {"text": word + " "})
            await asyncio.sleep(0.03)
        context = {
            "visual": {"status": "camera_off"},
            "text": {"top2": [["neutral", 0.6]]},
            "agreement": "n/a",
            "tone_mode": "coach",
            "note": "v0 stub: no real signals yet.",
        }
        yield sse("done", {"message_id": message_id, "context": context})

    return StreamingResponse(events(), media_type="text/event-stream")