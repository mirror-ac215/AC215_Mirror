# Mirror: shared project context

Paste this file at the start of any LLM session, followed by your own `brief_<name>.md`.

## What we are building

Mirror is a prototype web app for AC215 (Harvard, Fall 2026), not a clinical product. A patient chats with a direct, supportive persona. If the patient consents, their webcam feeds a facial-expression model, and the emotional tone of their text is scored too. Both signals are combined into **one bounded, uncertainty-labelled context object per chat turn**, and that object shapes the persona's reply. A clinician dashboard shows each patient's affect trend across sessions and a "needs review" marker.

## Implementation-status rule

This document describes the **target architecture and shared contracts**. It
does not mean that every pictured service, Compose configuration, deployment
asset, or test is already merged into `main`. Treat the repository's default
branch as the implementation source of truth and open pull requests as
unmerged work. The next section lists, by date, what is merged and what is
still in review.

When a component PR merges, update its README, lockfile/runtime declaration,
Docker and CI handoff, and the relevant contract or documentation in the same
delivery cycle, and update the status section below. This keeps the target
diagram from being mistaken for a statement that the complete product is
already runnable.

## Current status (MS3, updated Oct 26, 2026)

**On `main` (merged):** the MS2 foundation: contracts, Python service template,
shared CI with the required `CI summary` check, DVC metadata and reproducible
data jobs (FER-2013, persona data), the CV evaluation job (M2-08, FER-2013 guard
>= 0.64) and the cv-train baseline (M2-17), the Compose v0 stack (frontend,
api-gateway, db, mock llm-service; cv-service as the credentialed `cv` profile),
MS2 evidence and mock-up, and the M2-07 crop-alignment evaluation protocol (#41).
No MS3 feature has merged yet.

**Open pull requests** (merge order matters where noted):

| PR | Task | Owner | What it brings | Waiting on |
|---|---|---|---|---|
| #52 | M3-04 smoothing + gating | Mostafa | `api-gateway/app/gating.py`: 10 s window -> `ok` / `uncertain` / `dropped` / `camera_off`; thresholds in config | Owen's review |
| #55 | M3-18 CV baselines | Mostafa | cv-eval `--dataset-version/--threshold/--report-only/--device`; Aff-Wild2 prep (split by video); FER+ relabel; v3 scores Aff-Wild2 test 0.260, FER+ test 0.609 | Owen's review (merge first) |
| #56 | M3-01 part 1 | Mostafa | cv-train: several datasets with shares, start from a checkpoint, select by val macro-F1, bf16 | Owen's review (after #55) |
| #57 | M3-01 parts 2-3 | Mostafa | FER+ soft labels, cosine schedule, weight averaging, cv-eval `--model-version`; **v4** results; D-005; stacked on #55 + #56 | Owen's review (after #56) |
| #51 | M3-08 prompt template | Julie | context object -> prompt, 20 sample cases; placed in the api-gateway | Julie: add D-004 + Owen's fail-closed rule; then Mostafa runs the 20 cases on the real GPU model |
| #50 | M3-05 text emotion | Julie | j-hartmann DistilRoBERTa module in the gateway (D-003) | Julie: pin the model revision + Owen's two robustness fixes |
| #49 | M3-07 crisis check | Julie | deterministic text safety check before the LLM | Julie: recall/false-positive fixes; Mostafa: decide whether `medical`/`support` events stay in M3-07 |
| #43 | M3-13 GPU VM Stage A | Owen | provisioning, NVIDIA bootstrap, prod Compose, Caddy | Owen: rebase, fix `docker.list`, restrict 80/443 until real auth (M4-02) |

**Decisions in flight:** D-004 (face vs text disagreement: the more concerning
signal leads, the face only when the gate says ok; arrives with #51) and D-005
(soft-label CV models are guarded on FER+ test >= 0.609, FER-2013 reported;
arrives with #57).

**CV model:** cv-service still serves **v3** (`cv-vit-b16-v3`). **v4**
(`cv-vit-b16-v4`, ViT-B/16 fine-tuned on Aff-Wild2 video frames + FER+ soft
labels) is published at `gs://mirror-ac215-data/models/cv/v4/vit_b16_v4.pth`:
test macro-F1 Aff-Wild2 0.337 (v3 0.260), FER+ 0.720 (v3 0.609), FER-2013 0.588
(v3 0.645). It is not served yet; switching cv-service is integration work
(M3-03 / M3-10). Fear and sadness on video stay weak for every model tried (a
data limit: 16-28 training people per rare emotion), so the face signal must not
drive those emotions on its own. Starting instead from HSEmotion (an
EfficientNet-B2 pre-trained on ~400k AffectNet faces, research-use weights) gave
the same video ceiling (about 0.32 on validation) and weaker photo scores, so v4
stays the model (details in `pipelines/cv-train/README.md`, #57).

**Data notes:** Aff-Wild2 is licensed and stays local (not in DVC or the
bucket); FER+ labels come from Microsoft's `fer2013new.csv` (MIT) matched to
FER-2013 by pixels. Both are rebuilt with `mirror-prepare-affwild2` and
`mirror-prepare-ferplus` (#55, #57).

**Safety rule:** a deterministic check on the patient's *text* runs before the LLM. When it fires, it shows crisis resources (988), withholds the persona reply, and sets a review flag. The face model never triggers it. There are no real-time alerts and no emergency automation.

Inherited assets:

| Asset | Details |
|---|---|
| CV model | PyTorch; FER-2013, 7 classes; best about 67% accuracy, 0.64 macro-F1; ViT-B/16, EfficientNet-B0 and MobileNetV3 checkpoints (v3). Retrained as v4 in MS3, see Current status |
| Persona LLM | Qwen2.5-3B-Instruct with a QLoRA adapter (r=32) trained on about 380 prompt/response pairs |

## Team

| Person | Role |
|---|---|
| Mostafa | Coordinator, product and integration: api-gateway orchestration, smoothing/gating and fusion, CV model retraining (cv-train, Aff-Wild2 + FER+) and CV model card, self-report check-in, frontend shell and clinician dashboard (from the Lovable prototype), docker-compose integration, milestone submissions |
| Owen | Platform and backend: repo, service template, GCP, shared CI/CD, GPU VM deployment, llm-service, database, auth, clinician API, E2E tests; data pipeline and DVC, cv-service serving, CV evaluation; chat endpoint and webcam capture |
| Julie | LLM and NLP: persona data, LoRA retrain on Vertex AI, prompt template, text-emotion module, crisis-check rules, chat UI, fairness audit, evaluation, load test, monitoring dashboard, demo video |

The team is three people since Oct 13, 2026. The frontend is split across the team: Mostafa builds the app shell and the clinician dashboard, Owen the webcam capture, and Julie the chat screen.

**MLOps is shared: "you build it, you ship it."** Whoever owns a container or job also owns its MLOps work:
- its Dockerfile and uv lockfile
- its tests and its CI job
- its data or model versioning
- its logs and `/metrics` endpoint
- its README

Owen owns the shared platform the rest of us plug into: the template, the GCP project, the CI/CD pipeline and the VM.

## Architecture

```
Browser (React)
  |  HTTPS
Caddy proxy ── /      -> frontend (Node/Nitro SSR, :3000)
            └─ /api   -> api-gateway (FastAPI, :8000)
                           ├─ cv-service   (FastAPI + PyTorch CPU, :8001)
                           ├─ llm-service  (vLLM / transformers + LoRA, GPU, :8002)
                           └─ db           (Postgres, :5432)
Jobs (run on demand, not always on):
  data-preprocess, persona-data, cv-train, fairness-audit, llm-finetune, llm-eval, load-test, e2e
Storage: GCS bucket (data via DVC, model versions under gs://<bucket>/models/<name>/<version>/)
Tracking: Weights & Biases team "mirror"
Deploy: one GCP VM with a T4 GPU running docker compose; images in Artifact Registry tagged by git SHA
```

## One chat turn, step by step

1. While the camera is on, the frontend sends a downscaled JPEG to `POST /api/sessions/{id}/frames` every 1-2 s.
2. The gateway forwards each frame to `cv-service /predict` and keeps the probabilities in a short in-memory window. Frames are never stored.
3. The patient sends text to `POST /api/sessions/{id}/messages`.
4. The gateway runs these steps in order:
   - **Safety check.** If it fires: return the crisis payload, set a review flag, stop.
   - **Text-emotion module:** score the text.
   - **Smoothing and gating** over the visual window, giving `ok`, `uncertain`, `dropped` or `camera_off`.
   - **Fusion:** build the context object, including agreement and tone mode.
   - **Reply:** call `llm-service` with the prompt template plus the context object, stream the reply back over SSE, and store the message and an aggregated emotion window.
5. The clinician dashboard reads aggregated windows and review flags through `/api/clinician/*`.

Every failure falls back to a normal text-only reply: camera off, CV service down, low confidence, or LLM timeout.

## Contracts (the source of truth lives in docs/contracts; do not change them without the affected owners)

### cv-service `POST /predict`
Request: `multipart/form-data` with an `image` field (JPEG).

Response:
```json
{
  "face_found": true,
  "probs": {"angry":0.03,"disgust":0.01,"fear":0.05,"happy":0.10,"neutral":0.31,"sad":0.46,"surprise":0.04},
  "top2": [["sad",0.46],["neutral",0.31]],
  "margin": 0.15,
  "uncertain": false,
  "model_version": "cv-vit-b16-v3",
  "latency_ms": 42
}
```

### Context object (gateway -> llm-service, one per turn)
```json
{
  "visual": {"status": "ok", "top2": [["sad",0.46],["neutral",0.31]], "stability": 0.8, "window_s": 10, "n_frames": 8},
  "text":   {"top2": [["sadness",0.71],["neutral",0.12]]},
  "agreement": "agree",
  "tone_mode": "supportive",
  "note": "Estimates of expression, not facts about feelings."
}
```

Allowed values:
- `visual.status`: `ok`, `uncertain`, `dropped` or `camera_off`
- `agreement`: `agree`, `disagree` or `n/a`
- `tone_mode`: `coach` or `supportive`

The persona must never state the expression as a fact. When the signals disagree, it asks instead of assuming.

### Safety payload (gateway -> frontend, replaces the persona reply)
```json
{"type": "crisis", "message": "...", "resources": [{"name": "988 Suicide & Crisis Lifeline", "contact": "call or text 988"}], "review_flag_created": true}
```

### Database (no raw frames, ever)
| Table | Columns |
|---|---|
| `users` | id, role (`patient` or `clinician`), display_name, password_hash |
| `patients` | user_id, clinician_id |
| `sessions` | id, patient_id, started_at, ended_at, camera_consent |
| `messages` | id, session_id, role, text, created_at, safety_hit |
| `emotion_windows` | id, session_id, ts, visual_status, visual_top2 (json), text_top2 (json), tone_mode |
| `review_flags` | id, patient_id, message_id, created_at, reviewed_at, reviewed_by |

## Repository layout

```
mirror/
  services/_template/        FastAPI + uv + Dockerfile skeleton (copy this)
  services/frontend/         React (Node, not uv)
  services/api-gateway/      orchestrator; modules: safety/, text_emotion/, gating/, fusion/
  services/cv-service/
  services/llm-service/
  services/db/               init.sql, seed.sh, entrypoint-wrapper.sh
  pipelines/data-preprocess/ pipelines/persona-data/ pipelines/cv-train/
  pipelines/fairness-audit/  pipelines/llm-finetune/  pipelines/llm-eval/
  infra/compose.yml  infra/caddy/  infra/monitoring/  infra/pulumi/ (optional)
  tests/e2e/  tests/load/
  docs/architecture.md  docs/contracts/  docs/model_cards/  docs/decisions.md
  secrets/                   gitignored; README explains what goes here
  .github/workflows/         ci.yml, deploy.yml
```

## Conventions

**Environment and packages.** Each Python folder is its own uv project using Python 3.11, with `pyproject.toml` and `uv.lock` committed. Run `uv` commands from that component's folder (for example, `services/llm-service` or `docs/contracts`), not from the repository root unless the command explicitly names a project.
- Set up a component after cloning with `uv sync --frozen` in that component's folder.
- Run component code with `uv run python ...` in that component's folder.
- Add a package from that component's folder with `uv add <package>`; commit both its `pyproject.toml` and `uv.lock`.
- Never use pip or conda in the project.

**Config and secrets.** Configuration comes from environment variables via pydantic-settings. Commit `.env.example` and never `.env`. Secrets are mounted read-only from `secrets/`.

**Services.** Every service exposes `GET /health` and `GET /metrics`, and writes JSON logs that carry `X-Request-ID`.

**Tests and CI.** CI detects which component changed, then runs that component's required locked install, lint, test, and/or build checks. The stable `CI summary` fails if changed-path detection or an applicable check does not succeed. Formal contract changes run the contract validator and its tests; they do not require a service Docker build.

**Git workflow.**
- Branch name: `<initials>/<task-id>-short-name`.
- Commit messages start with the task ID.
- Each PR needs one reviewer and green CI.

### Dockerfile pattern (Python services)
```dockerfile
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# install dependencies first so this layer is cached when only code changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY . .
RUN uv sync --frozen --no-dev
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Milestones and build gates

| Milestone | Dates | Gate / focus |
|---|---|---|
| MS2 MLOps infrastructure | Oct 5 - 18 | **v0:** every container runs with `/health`; data pipelines are reproducible (DVC); CI runs on PRs |
| MS3 Integration and deployment | Oct 19 - Nov 8 | **v1:** frame goes through CV, then gate plus text emotion, then the context object, then the LLM; safety check; first deployment on a GCP VM |
| MS4 Design and development | Nov 9 - 29 | **v2:** dashboard on real data, auth, fallbacks, end-to-end test in CI, CD, load test, monitoring, evaluation, model cards |
| MS5 Final | Nov 30 - Dec 12 | Polish and demo; the stretch features (RAG, avatar, licensed voice) stay in scope and are built behind feature flags once v2 is stable |

## Oral checks (MS2-MS4)

A TF may ask any of us about any part of the project. Each of us needs to be able to say, in our own words: "This component takes X as input, does Y, and passes Z to the next part."

"Claude did that for me" is explicitly not accepted. Use your LLM to learn, not just to produce code.
