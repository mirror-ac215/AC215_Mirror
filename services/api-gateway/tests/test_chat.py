import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.chat import settings
from app.main import app

PATIENT = {"Authorization": "Bearer dev-patient-token"}
CLINICIAN = {"Authorization": "Bearer dev-clinician-token"}
PATIENT_B = {"Authorization": "Bearer dev-patient-b-token"}
FRAME = {"image": ("frame.jpg", b"fake-jpeg-bytes", "image/jpeg")}


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def new_session(c: AsyncClient, consent: bool = True) -> str:
    response = await c.post("/sessions", json={"camera_consent": consent}, headers=PATIENT)
    assert response.status_code == 201
    return response.json()["session_id"]


@pytest.mark.anyio
async def test_login_gives_role_token_and_seeded_user_id() -> None:
    async with client() as c:
        response = await c.post(
            "/auth/login",
            json={"email": "clinician.ada@example.test", "password": settings.mirror_demo_password},
        )
    assert response.status_code == 200
    assert response.json()["role"] == "clinician"
    assert response.json()["access_token"] == "dev-clinician-token"
    assert response.json()["user_id"] == "00000000-0000-0000-0000-000000000101"


@pytest.mark.anyio
async def test_login_wrong_password_or_unknown_email_401() -> None:
    async with client() as c:
        wrong_password = await c.post(
            "/auth/login",
            json={"email": "clinician.ada@example.test", "password": "not-the-password"},
        )
        unknown_email = await c.post(
            "/auth/login",
            json={"email": "nobody@example.test", "password": settings.mirror_demo_password},
        )
    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401


@pytest.mark.anyio
async def test_login_malformed_email_422() -> None:
    async with client() as c:
        response = await c.post(
            "/auth/login",
            json={"email": "not-an-email", "password": settings.mirror_demo_password},
        )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_sessions_need_a_token_401_and_a_patient_403() -> None:
    async with client() as c:
        no_token = await c.post("/sessions", json={"camera_consent": True})
        clinician = await c.post(
            "/sessions", json={"camera_consent": True}, headers=CLINICIAN
        )
    assert no_token.status_code == 401
    assert clinician.status_code == 403


@pytest.mark.anyio
async def test_frame_accepted_202_only_with_consent() -> None:
    async with client() as c:
        with_consent = await new_session(c, consent=True)
        without = await new_session(c, consent=False)
        ok = await c.post(f"/sessions/{with_consent}/frames", files=FRAME, headers=PATIENT)
        conflict = await c.post(f"/sessions/{without}/frames", files=FRAME, headers=PATIENT)
        unknown = await c.post("/sessions/nope/frames", files=FRAME, headers=PATIENT)
    assert ok.status_code == 202
    assert ok.json() == {"visual_status": "ok"}
    assert conflict.status_code == 409
    assert unknown.status_code == 404


@pytest.mark.anyio
async def test_frame_rejects_non_jpeg_415_and_oversized_413() -> None:
    png = {"image": ("frame.png", b"fake-png-bytes", "image/png")}
    too_big = {"image": ("big.jpg", b"x" * (settings.max_frame_bytes + 1), "image/jpeg")}
    async with client() as c:
        session_id = await new_session(c, consent=True)
        wrong_type = await c.post(f"/sessions/{session_id}/frames", files=png, headers=PATIENT)
        oversized = await c.post(f"/sessions/{session_id}/frames", files=too_big, headers=PATIENT)
    assert wrong_type.status_code == 415
    assert oversized.status_code == 413


@pytest.mark.anyio
async def test_message_streams_tokens_then_done() -> None:
    async with client() as c:
        session_id = await new_session(c)
        response = await c.post(
            f"/sessions/{session_id}/messages", json={"text": "hello"}, headers=PATIENT
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = []
    for block in response.text.strip().split("\n\n"):
        event_line, data_line = block.split("\n")
        name = event_line.removeprefix("event: ")
        data = json.loads(data_line.removeprefix("data: "))
        events.append((name, data))

    assert events[0][0] == "token"
    assert "text" in events[0][1]
    assert events[-1][0] == "done"
    assert events[-1][1]["context"]["tone_mode"] in ("coach", "supportive")


@pytest.mark.anyio
async def test_other_patient_gets_403_on_someone_elses_session() -> None:
    async with client() as c:
        alex_session = await new_session(c)  # created with PATIENT (Alex)
        own_frame = await c.post(f"/sessions/{alex_session}/frames", files=FRAME, headers=PATIENT)
        bri_frame = await c.post(
            f"/sessions/{alex_session}/frames", files=FRAME, headers=PATIENT_B
        )
        bri_message = await c.post(
            f"/sessions/{alex_session}/messages", json={"text": "hi"}, headers=PATIENT_B
        )
    assert own_frame.status_code == 202
    assert bri_frame.status_code == 403
    assert bri_message.status_code == 403
