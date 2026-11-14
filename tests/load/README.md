# Load test (M4-07)

Five patients chat at once against the api-gateway, each with the camera on, as the board asks:
p95 time to a full reply under 5 s, and the camera adding at most 300 ms. Results go in
[`docs/perf.md`](../../docs/perf.md).

## What one simulated patient does

1. Logs in as one of the 5 seeded demo patients (`services/db/seed.sh`), one account each.
2. Starts a session with camera consent on (or off, see below).
3. Camera on: sends a frame every 1.5 s, as the browser does.
4. Sends an everyday message every 5-15 s and reads the streamed reply. Crisis, medication and
   camera wording are left out: those skip the model and would make replies look faster.

Next to Locust's own request stats, each message records two timings:

| Name | Until |
|---|---|
| `reply: first token` | the first `token` event |
| `reply: complete` | the `done` event |

A reply that ends in `crisis` or stops early counts as a failure.

## How the camera's overhead is measured

Run the same test twice, camera on and camera off. Same users, messages and pacing; the only
difference is the camera. Overhead = p95 first token (on) - p95 first token (off): the work the
camera adds to a turn (frame uploads competing for the gateway, the gate and fusion).

## Run it locally

cv-service downloads the face model from the team bucket, therefore it needs your Google login.
Without it, `/health` on port 8001 stays "unready" and every frame upload fails with 503. From the
repository root:

```bash
gcloud auth application-default login
export CV_GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gcloud/application_default_credentials.json"
docker compose -f infra/compose.yml --profile cv up --build -d
curl -s http://localhost:8001/health   # wait for "status":"ok" (the model is 343 MB)
cd tests/load
uv sync
# use the same demo password as the stack, if infra/.env sets one
export MIRROR_DEMO_PASSWORD="$(grep '^MIRROR_DEMO_PASSWORD=' ../../infra/.env | cut -d= -f2-)"
MIRROR_CAMERA=on  uv run locust -f locustfile.py --headless -u 5 -r 5 -t 3m --csv runs/camera-on
MIRROR_CAMERA=off uv run locust -f locustfile.py --headless -u 5 -r 5 -t 3m --csv runs/camera-off
uv run python -m mirror_load.report runs/camera-on_stats.csv runs/camera-off_stats.csv
```

The last command prints the rows for the results table in `docs/perf.md`. `runs/` stays out of Git.

Locally, llm-service is the mock: the camera overhead is meaningful, the reply time is not.

## Run it against the GPU VM

The reply-time target needs the real model. The VM is Mostafa's to run (paid cloud). Point
`--host` at the deployed gateway (`https://<host>/api`) and set `MIRROR_DEMO_PASSWORD` to the
VM's value. Note `MAX_NUM_SEQS=1` in `infra/compose.prod.yml`: the model answers one request at a
time, therefore 5 patients queue.

## Settings

| Variable | Default | What it does |
|---|---|---|
| `MIRROR_CAMERA` | `on` | `off` for the comparison run |
| `MIRROR_DEMO_PASSWORD` | `local-demo-password` | the demo patients' password; must match `infra/.env` if it sets one, or every login fails with 401 |
| `MIRROR_LOAD_FRAME` | unset | path to a JPEG to send; unset sends a plain grey frame |

The grey frame has no face: cv-service runs face detection, finds none, and the gate answers
"dropped". That still times the full camera path. To exercise the "ok" path, point
`MIRROR_LOAD_FRAME` at a consented photo kept outside the repository.

## Tests

```bash
uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check .
```

`tests/` covers the SSE timing and the report; the locustfile itself needs a running stack.
