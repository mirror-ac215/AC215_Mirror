# Mirror

An emotion-aware conversational companion with a clinician view.
AC215 (Harvard, Fall 2026) course project. **A prototype, not a clinical product.**

A patient chats with a supportive persona. With consent, their webcam gives a facial-expression signal and their text gives a tone signal. Both are smoothed, gated and fused into one short, uncertainty-labelled context note per message, and that note shapes the reply. A deterministic text-only safety check runs before the model: if it fires, the app shows crisis resources (988) and flags the conversation for the clinician. The clinician dashboard shows affect trends between sessions.

Team: Mostafa Galal, Owen Chong, Julie Lander.

## Milestone 4: what changed since MS3

MS4 turns the MS3 system into a complete application that runs locally with one command, backed by CI and automated tests.

| Area | What we added | Where |
|---|---|---|
| Application design | Screens and user flows, solution and technical architecture, data flow, sequence diagram, API summary, code organisation | [`docs/design.md`](docs/design.md) |
| One command, no setup | The whole local stack starts from a fresh clone with built-in, local-only defaults | [Quick start](#quick-start) |
| Clinician side | Endpoints that enforce which patients a clinician may see, and a dashboard on real data with uncertainty shown | `services/api-gateway/app/clinician.py`, `services/frontend` |
| Loading and errors | Visible loading and error states on the sign-in and chat screens; every chat turn finishes, even with a service down | `services/frontend`, `services/api-gateway/app/orchestration.py` |
| Safety | A second crisis layer that matches by meaning, after the fixed rules. If its model cannot load, the rules and 988 still work and `/health` reports degraded | `services/api-gateway` |
| Conversation | When face and words disagree, Mirror checks in at most once every few turns (D-004) | `services/api-gateway/app/fusion.py` |
| CI | Every pull request to `main` is linted, built and tested; one required check covers all of it | [`.github/workflows/ci.yml`](.github/workflows/ci.yml) |
| Tests | Unit, integration, system and browser end-to-end tests; 70% coverage gate on the three backend services (the course asks for 50%) | [`docs/testing.md`](docs/testing.md) |
| Evaluation | LLM model card, pairwise preference scoring, and a load test with local results | [model card](docs/model_cards/qwen2.5-3b-instruct.md), `pipelines/llm-eval/pairwise`, [`docs/perf.md`](docs/perf.md) |
| Monitoring | Prometheus and a Grafana dashboard for the gateway (opt-in) | [`infra/monitoring/README.md`](infra/monitoring/README.md) |

### Components

| Component | What it does | Local address |
|---|---|---|
| `frontend` | React web app: sign-in, consent, chat, crisis screen, clinician dashboard | http://localhost:3000 |
| `api-gateway` | FastAPI: login, sessions, safety rules, gating, fusion, chat streaming, clinician endpoints | http://localhost:8000 (docs at http://localhost:8000/docs) |
| `llm-service` | The language model. Locally a mock; Qwen on vLLM when deployed with a GPU | internal only |
| `db` | Postgres with a seeded demo database | internal only |
| `cv-service` (opt-in, `--profile cv`) | The face-expression model; needs Google Cloud access to download it | http://localhost:8001 |
| Grafana (opt-in, `--profile monitoring`) | Gateway dashboard | http://localhost:3001 |

Every component has its own Dockerfile or pinned image and starts from `infra/compose.yml`.

### Use the app

After the [Quick start](#quick-start), open http://localhost:3000.

- **As a patient** (`patient.alex@example.test`): sign in, choose whether to allow the camera, and send a message. The reply streams in word by word. Without `cv-service` the chat works from text alone.
- **As a clinician** (`clinician.ada@example.test`): sign in to see your assigned patients, their affect trends and any conversations flagged for review.

Local replies come from the mock model, so they show the flow and not the real model's quality. Stop the stack with `docker compose -f infra/compose.yml down`. Screens and user flows: [design document](docs/design.md#1-user-interface-and-user-flows).

### CI and tests

On every pull request, GitHub Actions finds the changed components and runs their lint, build and tests. The browser end-to-end test (patient to clinician) runs the real containers on every pull request; the Compose smoke test and the database checks run when files that affect them change. The required `CI summary` check fails if any job fails, and `main` only accepts reviewed pull requests with that check green. Coverage for each backend service is printed in the run's Summary page.

To run the tests yourself: [`docs/testing.md`](docs/testing.md).

### Known gaps at MS4

- **Reply time on the real model is not measured yet.** Locally the camera adds 90 ms to the p95 first token (limit 300 ms); the reply-time target (p95 under 5 s) needs a run on the GPU VM, planned for MS5 ([`docs/perf.md`](docs/perf.md)).
- **Kubernetes:** the GKE files are in `infra/k8s`, but nothing has been deployed to a cluster yet (MS5).
- **Coverage gate:** it covers the three backend services. The frontend and pipelines are tested in CI without a coverage threshold.

## Milestone 3: what changed since MS2

| Area | What we added | Where |
|---|---|---|
| Face model | v4, retrained on Aff-Wild2 video frames plus FER+ crowd labels. Test macro-F1: video 0.260 -> 0.337, FER+ 0.609 -> 0.720. A release check blocks any model below 0.609 on FER+ (D-005). | `pipelines/cv-train`, `pipelines/cv-eval`, [model card](docs/model_cards/cv-vit-b16-v4.md) |
| Face signal in the chat | A gate that passes a face reading only when it is steady over 10 seconds (thresholds from a W&B sweep on held-out video), and fusion of face and text into one context note per message | `services/api-gateway/app/gating.py`, `app/fusion.py` |
| Text and safety | Text-emotion model (D-003). Crisis, medication and camera rules run before the LLM; 162 test messages run in CI | `app/text_emotion.py`, `app/safety.py`, `tests/safety_cases.yaml` |
| Language model | Plain Qwen 2.5-3B-Instruct on vLLM (D-006), prompt v7 with a question filter, and a LoRA fine-tuning job for Vertex AI | `services/llm-service`, `app/prompt.py`, `pipelines/llm-finetune` |
| The app | Chat end to end with streamed replies, webcam capture with consent, login with roles from the database (an MS4 task, done early) | `services/frontend`, `app/chat.py`, `app/auth.py` |
| Data | IEMOCAP as a DVC stage; FairFace fairness audit of v4 | `pipelines/iemocap-data`, `pipelines/fairness-audit` |
| Deployment | A merge to `main` publishes images tagged with the commit to Artifact Registry when the repository's Artifact Registry variables are configured (otherwise the workflow skips publishing); a GPU VM runs them behind Caddy (HTTPS) | `.github/workflows/publish-artifact-registry-images.yml`, `infra/` |
| Monitoring | Container logs in Cloud Logging; private Prometheus metrics | [`docs/monitoring.md`](docs/monitoring.md) |

Screenshots of the running system: [`docs/evidence/`](docs/evidence/README.md) (MS3 section).

### Reproduce a training run

**Face model, tracked in W&B** (log in once with `wandb login`; runs go to the `mirror` project). A smoke run:

```bash
cd pipelines/cv-train
uv sync
uv run mirror-cv-train --params params.yaml --data-dir ../../data/processed/fer2013/v1 --output outputs/smoke.pth --epochs 1 --max-batches 2 --no-pretrained
```

This smoke run uses FER-2013 only (restored by `dvc pull`). The full v4 recipe needs locally built Aff-Wild2 frames (licensed) and the v3 checkpoint; see the [cv-train README](pipelines/cv-train/README.md). Check a trained model with `mirror-cv-release-check` in `pipelines/cv-eval`. All 8 v4 runs and their settings are in the cv-train README.

**Language model on Vertex AI** (serverless, one L4 GPU, W&B key from Secret Manager), from `pipelines/llm-finetune`:

The first command only prints the job spec; the second submits it.

```bash
uv run --extra vertex mirror-llm-finetune submit \
  --data-uri gs://mirror-ac215-data/data/processed/persona/v1 --dry-run
uv run --extra vertex mirror-llm-finetune submit \
  --data-uri gs://mirror-ac215-data/data/processed/persona/v1
```

The job is set up and its dry run works, but **no Vertex run has completed yet**: there was no GPU capacity when we submitted. Full setup in the [llm-finetune README](pipelines/llm-finetune/README.md).

### Run the ML pipeline

We use DVC rather than Vertex AI Pipelines. `dvc.yaml` rebuilds the data stages (`fer2013_preprocess`, `persona_clean`, `iemocap_build`), each reproducible by hash; training and evaluation then run as the tracked jobs above.

`dvc repro` rebuilds only the stages whose code, parameters or inputs changed; `dvc status` should then print "Data and pipelines are up to date."

```bash
dvc pull
dvc repro
dvc status
```

### Deploy

1. Merge to `main`: GitHub Actions publishes every image tagged with the commit SHA, if the Artifact Registry variables are configured (otherwise it skips publishing).
2. On the GPU VM: check out that commit, set `MIRROR_IMAGE_TAG` to it in `infra/.env.prod`, and run `bash infra/deploy-stage-b.sh`. It checks that the VM can read the model and write logs, pulls the images by tag and starts them with health checks.
3. Stop the VM after use: it costs about $0.70 an hour while running.

First-time VM setup, recovery and what to do when a GPU zone has no capacity: [`infra/README.md`](infra/README.md).

### Use the API

All endpoints are described in [`docs/contracts/api-gateway.openapi.yaml`](docs/contracts/api-gateway.openapi.yaml); a running gateway also serves them at `/docs`.

| Endpoint | What it does |
|---|---|
| `POST /auth/login` | Email and password in, a short-lived token with the user's role out |
| `POST /sessions` | Starts a chat session (`camera_consent`: true or false) |
| `POST /sessions/{id}/frames` | One webcam JPEG (only with camera consent); returns 202 |
| `POST /sessions/{id}/messages` | One message in; the reply streams back as `token` events, then a `done` event with the context, or one `crisis` event |
| `GET /health` | The gateway and its dependencies |

Locally the API is `http://localhost:8000`; on the deployed site use `https://<CADDY_DOMAIN>/api`.

```bash
API=http://localhost:8000
TOKEN=$(curl -s $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"patient.alex@example.test","password":"<MIRROR_DEMO_PASSWORD>"}' | jq -r .access_token)
SID=$(curl -s $API/sessions -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"camera_consent":false}' | jq -r .session_id)
curl -sN $API/sessions/$SID/messages -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"text":"It has been a long week."}'
```

Tests: every service has its own unit tests, and CI runs them plus contract validation, a database test and a smoke test of the whole stack on every pull request.

### Known gaps at MS3

- **Vertex AI training:** the job is ready but has not completed a run (no GPU capacity).
- **Serverless deployment:** not used. The language model needs a GPU, and a VM keeps the model loaded between requests.
- **The VM runs on demand:** it is stopped between demos to save cost, so the site is not always up.

## Repository layout

| Folder | What lives there |
|---|---|
| `services/` | Long-running containers: `frontend`, `api-gateway`, `cv-service`, `llm-service`, `db`, plus `_template` to copy from |
| `pipelines/` | Jobs that run on demand: data preprocessing, training, fairness audit, evaluation |
| `infra/` | docker-compose, reverse proxy, monitoring, deployment config, Kubernetes files (`k8s`) |
| `tests/` | End-to-end (`e2e`) and load (`load`) tests |
| `docs/` | Architecture and project context, API contracts, model cards, decisions |
| `secrets/` | Keys and credentials. **Never committed**; see `secrets/README.md` |

For the application design (screens and user flows, architecture, data flow, a sequence diagram, the API table and the code layout), see [`docs/design.md`](docs/design.md).

Start with [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md). It covers:
- the architecture;
- what happens on one chat turn;
- the API contracts;
- our conventions.

## Quick start

The local stack (frontend, api-gateway, llm-service in mock mode, db) runs with Docker Compose. Details,
configuration and troubleshooting are in [`infra/README.md`](infra/README.md).

For the production deployment on a GPU VM, see [Deploy](#deploy) above.

```bash
git clone https://github.com/mirror-ac215/AC215_Mirror.git
cd AC215_Mirror
docker compose -f infra/compose.yml up --build -d
```

No setup is needed: the local stack uses built-in, local-only defaults. Open http://localhost:3000 (app) and http://localhost:8000/docs (gateway API), and log in as `patient.alex@example.test` or `clinician.ada@example.test` with the password `local-demo-password`. To use your own passwords, see [`infra/README.md`](infra/README.md).
`cv-service` is opt-in (`--profile cv`) because it downloads the model from GCS; see `infra/README.md`.

To run the tests (every suite, locally and in CI): [`docs/testing.md`](docs/testing.md).

## Data setup with DVC

Raw datasets are versioned with DVC, while the actual content is stored in the team's GCS bucket. Raw data is never committed to Git.

Install DVC once (with its Google Cloud Storage plugin), authenticate once for the GCS backend, then retrieve the tracked dataset version:

```bash
uv tool install --reinstall --with dvc-gs dvc
gcloud auth application-default login
dvc pull
```

`dvc pull` restores these raw inputs, plus the processed outputs of all three pipeline stages (`data/processed/fer2013/v1`, `data/processed/persona/v1`, `data/processed/iemocap/v1`):

```text
data/raw/fer2013/archive.zip
data/raw/persona/jbp_clean_full.csv
data/raw/persona/jbp_train.csv
data/raw/persona/jbp_val.csv
data/raw/persona/jbp_test.csv
data/raw/iemocap/IEMOCAP_full_release.tar.gz
```

To check that code, parameters and data are in sync, and to rebuild a stage from the raw data:

```bash
dvc status
dvc repro persona_clean
```

The stages are defined in `dvc.yaml` (`fer2013_preprocess`: FER-2013 split and resize; `persona_clean`: persona filter, dedupe and split; `iemocap_build`: IEMOCAP evaluation table). Rebuilding gives byte-identical outputs on Linux, macOS and Windows, so `dvc.lock` does not change.

The DVC remote is `mirror_gcs` at `gs://mirror-ac215-data/dvc`. Do not run `git add data/`; commit only the DVC configuration and `.dvc` metadata files.

## How we work

- **One task, one branch, one pull request.** Name the branch `<initials>/<task-id>-short-name`, for example `mg/M1-03-repo-skeleton`.
- **Merging into `main`.** Every pull request needs green CI and an approval from a maintainer (Mostafa or Owen, see `.github/CODEOWNERS`). No direct pushes.
- **Environments.** Every Python component is its own uv project: `pyproject.toml` and `uv.lock` are committed, and `.venv/` is not.
- **What stays out of git.** Secrets, raw data and model weights never go in. Data is tracked with DVC and models are stored in GCS.
