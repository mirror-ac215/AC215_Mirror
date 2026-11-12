# Mirror

An emotion-aware conversational companion with a clinician view.
AC215 (Harvard, Fall 2026) course project. **A prototype, not a clinical product.**

A patient chats with a supportive persona. With consent, their webcam gives a facial-expression signal and their text gives a tone signal. Both are smoothed, gated and fused into one short, uncertainty-labelled context note per message, and that note shapes the reply. A deterministic text-only safety check runs before the model: if it fires, the app shows crisis resources (988) and flags the conversation for the clinician. The clinician dashboard shows affect trends between sessions.

Team: Mostafa Galal, Owen Chong, Julie Lander.

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
| `infra/` | docker-compose, reverse proxy, monitoring, deployment config |
| `tests/` | End-to-end (`e2e`) and load (`load`) tests |
| `docs/` | Architecture and project context, API contracts, model cards, decisions |
| `secrets/` | Keys and credentials. **Never committed**; see `secrets/README.md` |

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
cp infra/.env.example infra/.env
docker compose -f infra/compose.yml up --build -d
```

Fill in the two values in `infra/.env` before starting. Then open http://localhost:3000 (app) and http://localhost:8000/docs (gateway API).
`cv-service` is opt-in (`--profile cv`) because it downloads the model from GCS; see `infra/README.md`.

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
