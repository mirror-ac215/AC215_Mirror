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

## Smoothing and gating (M3-04)

`app/gating.py` keeps the last 10 s of cv-service readings per session (probabilities only, never frames) and reports `ok`, `uncertain`, `dropped` or `camera_off`. "ok" needs the averaged top emotion to reach `GATE_MIN_TOP_PROB` (0.45), lead the second by `GATE_MIN_MARGIN` (0.05), and be the top emotion in `GATE_MIN_STABILITY` (0.50) of the frames.

**How the thresholds were chosen:** `scripts/gate_sweep.py` replays the 36 held-out Aff-Wild2 validation videos at 1 frame per second (1,951 ten-second windows) through the real `gate()`, scored by the current CV model (`cv-vit-b16-v4`, per-frame scores from `pipelines/cv-eval/scripts/export_frame_probs.py`), and tries 80 combinations ([W&B](https://wandb.ai/mog941-harvard-university/mirror/runs/dposf012)).

| Thresholds (top / margin / stability) | "ok" in | right when "ok" |
|---|---|---|
| 0.30 / 0.05 / 0.50 (loose) | 71 % of windows | 54 % |
| 0.40 / 0.10 / 0.60 (first guess) | 47 % | 59 % |
| **0.45 / 0.05 / 0.50 (chosen)** | **31 %** | **64 %** |
| 0.50 / 0.05 / 0.50 (strict) | 14 % | 69 % |

A single frame without the gate is right 50 % of the time. We chose fewer but more reliable face signals: a wrong hint is worse than none, because Mirror then relies on the text. When the gate says "ok" it reports almost only neutral, happy or surprise; it is almost never "ok" for angry, sad, fear or disgust, so fusion (M3-06) should not let the face lead on those.

Re-run after a model change: export the frame scores with the new checkpoint, then `uv run --with wandb python -m scripts.gate_sweep <frames.csv> --wandb-project mirror`.

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
