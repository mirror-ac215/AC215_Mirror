# Monitoring

Basic production monitoring for MS3. Grafana dashboards are planned for MS4 (M4-08).

## What is monitored

| Source | What it records | Where to find it |
| --- | --- | --- |
| api-gateway logs | Each request's path, status and time; errors such as `cv_prediction_failed`, `text_emotion_load_failed` and `chat_persistence_orchestration_failed`; safety hits as `safety_hit kind=crisis rule=...`, `kind=medication` or `kind=camera` (the rule id only, never the message) | Cloud Logging |
| llm-service logs | vLLM startup, errors, request status and throughput | Cloud Logging |
| cv-service logs | Model startup failures; each request's path, status and time | Cloud Logging |
| frontend and caddy logs | Startup and errors | Cloud Logging |
| api-gateway metrics | Requests, response time, crisis, medication and camera hits (`mirror_gateway_camera_hits_total` counts fixed camera replies and has no labels or message text), text emotion time and failures, gate and fusion outcomes | `/metrics` on the VM |
| llm-service metrics | Running and waiting requests, plus vLLM's own performance metrics | `/metrics` on the VM |
| cv-service metrics | Request counts from its own `/metrics` | `/metrics` on the VM |

The database is not sent to Cloud Logging. Its logs stay on the VM, read with `docker compose logs db`.

## Viewing logs

Logs are kept for 30 days in the project's default log bucket. You need access to the `mirror-ac215` project.

**In the browser:** open [Logs Explorer](https://console.cloud.google.com/logs/query?project=mirror-ac215) and run a query.

All container logs:

```text
logName="projects/mirror-ac215/logs/gcplogs-docker-driver"
```

One service (use `api-gateway`, `llm-service`, `cv-service`, `frontend` or `caddy`):

```text
logName="projects/mirror-ac215/logs/gcplogs-docker-driver"
jsonPayload.container.name:"api-gateway"
```

Errors in the gateway:

```text
logName="projects/mirror-ac215/logs/gcplogs-docker-driver"
jsonPayload.container.name:"api-gateway"
jsonPayload.message:"ERROR"
```

Crisis hits (use `kind=medication` or `kind=camera` for the other two):

```text
logName="projects/mirror-ac215/logs/gcplogs-docker-driver"
jsonPayload.message:"safety_hit kind=crisis"
```

**From a terminal:**

```bash
gcloud logging read 'logName="projects/mirror-ac215/logs/gcplogs-docker-driver" AND jsonPayload.container.name:"api-gateway"' --project mirror-ac215 --limit 20 --freshness 1d
```

**On the VM:** `docker compose logs` still works alongside Cloud Logging.

## Viewing metrics

Metrics are not public: Caddy returns 404 for `/api/metrics`, and the services have no public ports. Run these on the VM from the repository root:

```bash
compose="docker compose --env-file infra/.env.prod -f infra/compose.yml -f infra/compose.prod.yml -f infra/compose.registry.yml"
$compose exec api-gateway python -c "import urllib.request as u; print(u.urlopen('http://localhost:8000/metrics').read().decode())"
$compose exec llm-service python3 -c "import urllib.request as u; print(u.urlopen('http://localhost:8002/metrics').read().decode())"
$compose exec cv-service python -c "import urllib.request as u; print(u.urlopen('http://localhost:8001/metrics').read().decode())"
```

## What must stay out of the logs

Patient messages, replies, camera frames, passwords and tokens must never be logged. A crisis hit records that a rule fired and the session ID in the request path, not what was said.

vLLM's `--enable-log-requests` writes prompts to its logs, so it must stay off. It is off by default.

## Setup

The VM's service account needs permission to write logs. A project administrator runs this once:

```bash
gcloud projects add-iam-policy-binding mirror-ac215 --member="serviceAccount:mirror-vm-runtime@mirror-ac215.iam.gserviceaccount.com" --role="roles/logging.logWriter" --condition=None
```

Docker refuses to start a container if it cannot reach Cloud Logging, so `infra/deploy-stage-b.sh` checks this permission before starting anything and stops with a clear message if it is missing.

For a local run of the production compose files, which has no access to Cloud Logging, use an override file that sets `logging: !reset {}` on these services.
