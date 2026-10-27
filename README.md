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

Defaults use docker-compose service names. No secrets needed in v0. All variables are listed in `.env.example`; copy it to `.env` only for local overrides (never commit `.env`).

## Checks

```bash
uv run ruff check .
uv run pytest -q
```

## Prompt template (M3-08)

`app/prompt.py` turns one context object and the patient's message into the messages the gateway sends to llm-service. It lives in the gateway, not in llm-service (see `docs/architecture.md`): the gateway owns the context object, and llm-service stays a plain model server.

**What the model gets each turn**

1. Fixed rules: 2 to 4 sentences, at most one question, never claims to be a person or a clinician, no medical advice, never mentions cameras or numbers.
2. The mode, set by fusion (M3-06): **supportive** by default (listen, no advice), **coach** (encouraging, one small next step) only after sustained steady signals.
3. This turn's signals, as words and never as numbers, for example:
   - `Face: their expression may look sad. This is an estimate.`
   - `Face: the camera is off. Do not mention facial expression.`
   - `The face and the words point in different directions. Lean towards the more concerning one: check in once, gently ... If they have already answered, take their word for it and do not ask again.` (D-004)
4. The last 6 messages of the conversation, then the patient's new message.

**Why words, not numbers:** "0.46 sad" invites the model to say "you are 46% sad". Plain words plus "this is an estimate" keep it guessing and asking, the way the persona rules require.

**Weak readings are hidden, with no exceptions:** a top label under 0.40, or a label the template doesn't know, becomes "unclear". An `uncertain`, `dropped` or `camera_off` face reading always becomes "do not mention facial expression", even if the patient brings it up. An unknown label never fails the patient's turn.

**Safety:** the patient's text only goes in the `user` message, never in the system prompt. The history can't carry a `system` message. The crisis check (M3-07) runs before any of this.

**Review the 20 sample cases** (`tests/prompt_cases.json`):

```bash
uv run python -m scripts.prompt_samples > prompt_samples.md
uv run python -m scripts.prompt_samples --llm-url http://localhost:8002 > prompt_samples.md
```

The first command shows only the prompts. The second also asks llm-service for Mirror's reply to each case, giving 20 short transcripts for the team to review.

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
