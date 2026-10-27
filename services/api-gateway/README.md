# api-gateway

The only service the frontend calls. v0 (MS2): every endpoint from `docs/contracts/api-gateway.openapi.yaml` exists with the right shapes and status codes, but returns fake data. The real CV call, safety check, fusion and LLM call arrive in MS3.

## Run locally

```bash
uv sync
uv run uvicorn app.main:app --port 8000 --reload
```

Interactive API docs: http://localhost:8000/docs. Click **Authorize** and enter a demo token:

| User | Email | Token |
|---|---|---|
| Dr. Ada Chen (clinician) | `clinician.ada@example.test` | `dev-clinician-token` |
| Alex Rivera (patient) | `patient.alex@example.test` | `dev-patient-token` |
| Bri Santos (patient) | `patient.bri@example.test` | `dev-patient-b-token` |

Or get the token from `POST /auth/login` with one of these emails and the demo password.

## Endpoints (v0)

| Endpoint | Returns |
|---|---|
| `GET /health` | `ok` / `degraded` + each dependency (`cv-service`, `llm-service`, `db`); always 200 so Docker doesn't restart the gateway when a dependency is down |
| `POST /auth/login` | demo users from `services/db/seed.sh` with password `MIRROR_DEMO_PASSWORD`; returns their token, role and `user_id`; 401 if the email or password is wrong (real auth: M4-02) |
| `POST /sessions` | 201, in-memory session (database: MS3) |
| `POST /sessions/{id}/frames` | 202; frame read and discarded, never stored; 409 without camera consent; 415 if not JPEG; 413 if larger than MAX_FRAME_BYTES |
| `POST /sessions/{id}/messages` | Server-Sent Events: `token` events (`{"text": ...}`) then `done` |

Errors: 401 no/invalid token or wrong login, 403 wrong role or not your session, 404 unknown session, 409 no camera consent, 413 frame too large, 415 not a JPEG, 422 malformed request.

## Configuration (environment variables)

| Variable | Default |
|---|---|
| `APP_NAME` | `mirror-api-gateway` |
| `LOG_LEVEL` | `INFO` |
| `CV_SERVICE_URL` | `http://cv-service:8001` |
| `LLM_SERVICE_URL` | `http://llm-service:8002` |
| `DB_HOST` / `DB_PORT` | `db` / `5432` |
| `DEPENDENCY_TIMEOUT_S` | `2.0` |
| `MAX_FRAME_BYTES` | `1000000` |
| `MIRROR_DEMO_PASSWORD` | `mirror-demo` (local demo only; same variable as `services/db`) |
| `CORS_ORIGINS` | `["http://localhost:3000","http://localhost:8080"]` |

| `TEXT_EMOTION_MODEL` | `j-hartmann/emotion-english-distilroberta-base` (D-003) |
| `TEXT_EMOTION_REVISION` | `0e1cd914e3d46199ed785853e12b57304e04178b` (pinned Hugging Face commit, see Model pin) |
| `TEXT_EMOTION_MAX_CHARS` | `2000` |

Defaults use docker-compose service names. No secrets needed in v0. All variables are listed in `.env.example`; copy it to `.env` only for local overrides (never commit `.env`).

## Text-emotion module (M3-05)

`app/text_emotion.py` turns one chat message into the two most likely emotions, in the shape the context object uses for `text.top2` (`docs/contracts/context_object.schema.json`):

```python
from app.text_emotion import get_text_emotion

result = get_text_emotion().analyse("I had a really rough day")
result.as_context()   # {"top2": [["sadness", 0.71], ["fear", 0.12]]}
result.latency_ms     # time spent scoring this message
```

- **Model:** `j-hartmann/emotion-english-distilroberta-base`, chosen in M2-11 (D-003 in `docs/decisions.md`). Its 7 labels are the same as the camera model's: face and text can be compared in fusion (M3-06).
- **CPU only.** torch comes from the CPU wheel index (as in cv-service); the image doesn't carry CUDA.
- **Loaded lazily:** on the first message, or call `get_text_emotion().warm_up()` at startup to keep the first patient message fast. The model (~330 MB) downloads from Hugging Face on first load; mount a volume on `HF_HOME` to keep it between restarts.
- **Model pin:** `TEXT_EMOTION_REVISION` defaults to Hugging Face commit `0e1cd914e3d46199ed785853e12b57304e04178b` (the model's latest commit, Jan 2, 2023), not `main`, so a rebuild can't silently load different weights. **Deployment handoff:** the VM and docker-compose use this default; do not set `TEXT_EMOTION_REVISION=main` anywhere. To move to a newer model commit, change the default here, in `app/config.py` and in `.env.example` in one PR, and re-run the D-003 evaluation and the latency check before merging.
- **Failure:** if the model can't load or run, `analyse()` raises `TextEmotionUnavailable`. The chat endpoint (M3-10) should then carry on without a text signal (fallback paths: M4-04).
- **Safety:** this module only describes tone. The crisis check (M3-07) runs before it and never depends on it.
- **Privacy:** message text is never logged, only the top label and latency.

Tests: `tests/test_text_emotion.py` uses a fake classifier and runs in CI with no download. The real-model latency check (target: p95 < 100 ms per message on CPU) runs only when asked:

```bash
RUN_MODEL_TESTS=1 uv run pytest tests/test_text_emotion_model.py -q -s
```

## Checks

```bash
uv run ruff check .
uv run pytest -q
```

## Docker

Build and run from this directory:

```bash
docker build -t mirror-api-gateway .
docker run --rm -p 8000:8000 mirror-api-gateway
```

Check it from a second terminal:

```bash
curl -f http://localhost:8000/health
```

Run on its own, `/health` reports `degraded` because cv-service, llm-service and db aren't running. That's expected: the status code is still 200, so the container stays healthy. Inside docker-compose (M2-03) the dependencies resolve by service name.
