"""M4-07 load test: 5 patients chatting at once, each with the camera on (or all off).

Each simulated patient logs in as one of the 5 seeded demo patients, starts a session, sends a
camera frame every 1.5 s (as the browser does) and a message every 5-15 s. Two timings per
message are recorded next to Locust's own request stats:

- "reply: first token": until the first `token` event;
- "reply: complete": until the `done` event.

Run it twice, MIRROR_CAMERA=on then MIRROR_CAMERA=off, and compare with
`python -m mirror_load.report` (README.md, docs/perf.md).
"""

from __future__ import annotations

import io
import itertools
import os
import random
import time
from pathlib import Path

import gevent
from locust import HttpUser, between, events, task
from mirror_load.sse import time_reply
from PIL import Image

# The 5 seeded demo patients (services/db/seed.sh); one simulated patient per account.
PATIENTS = [
    "patient.alex@example.test",
    "patient.bri@example.test",
    "patient.casey@example.test",
    "patient.dev@example.test",
    "patient.eli@example.test",
]
_next_patient = itertools.cycle(PATIENTS)

# Everyday messages only: crisis, medication and camera wording would skip the model
# (app/safety.py) and make replies look faster than they are.
MESSAGES = [
    "Work has been a lot this week and I'm tired.",
    "I had a nice walk with my sister today.",
    "I keep putting off emails and then feeling bad about it.",
    "Sleep has been patchy, I wake up around 4.",
    "My flatmate and I had a small argument about the dishes.",
    "I'm looking forward to the weekend, a bit.",
    "I don't really know what to talk about today.",
    "I tried the breathing thing and it helped a little.",
]

CAMERA_ON = os.environ.get("MIRROR_CAMERA", "on").lower() == "on"
PASSWORD = os.environ.get("MIRROR_DEMO_PASSWORD", "local-demo-password")
FRAME_SECONDS = 1.5  # same as the browser (services/frontend/src/routes/session.tsx)


def frame_jpeg() -> bytes:
    """MIRROR_LOAD_FRAME if set (keep real face photos out of Git), else a plain grey frame.

    A grey frame has no face: cv-service still runs the face detector on it and the gate
    answers "dropped", which is enough to time the camera path.
    """
    path = os.environ.get("MIRROR_LOAD_FRAME")
    if path:
        return Path(path).read_bytes()
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (128, 128, 128)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


FRAME = frame_jpeg()


@events.test_start.add_listener
def describe_run(environment, **_kwargs):
    print(f"M4-07 load test: camera {'on' if CAMERA_ON else 'off'}, host {environment.host}")


class Patient(HttpUser):
    host = "http://localhost:8000"
    wait_time = between(5, 15)  # a person reading the reply and typing the next message

    def on_start(self) -> None:
        email = next(_next_patient)
        login = self.client.post(
            "/auth/login", json={"email": email, "password": PASSWORD}, name="/auth/login"
        )
        login.raise_for_status()
        self.client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        session = self.client.post(
            "/sessions", json={"camera_consent": CAMERA_ON}, name="/sessions"
        )
        session.raise_for_status()
        self.session_id = session.json()["session_id"]
        self.frames = gevent.spawn(self._send_frames) if CAMERA_ON else None

    def on_stop(self) -> None:
        if self.frames:
            self.frames.kill()

    def _send_frames(self) -> None:
        while True:
            self.client.post(
                f"/sessions/{self.session_id}/frames",
                files={"image": ("frame.jpg", FRAME, "image/jpeg")},
                name="/sessions/{id}/frames",
            )
            gevent.sleep(FRAME_SECONDS)

    @task
    def send_message(self) -> None:
        started = time.perf_counter()
        with self.client.post(
            f"/sessions/{self.session_id}/messages",
            json={"text": random.choice(MESSAGES)},
            name="/sessions/{id}/messages",
            stream=True,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"status {response.status_code}")
                return
            timing = time_reply(response.iter_lines(decode_unicode=True), started)
            if timing.outcome != "done":
                response.failure(f"reply ended with {timing.outcome}")
                return
            response.success()

        fire = self.environment.events.request.fire
        if timing.first_token_ms is not None:
            fire(
                request_type="SSE",
                name="reply: first token",
                response_time=timing.first_token_ms,
                response_length=0,
                exception=None,
                context={},
            )
        fire(
            request_type="SSE",
            name="reply: complete",
            response_time=timing.complete_ms,
            response_length=timing.tokens,
            exception=None,
            context={},
        )
