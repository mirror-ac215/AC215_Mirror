# Testing (MS4 Deliverable 5)

How Mirror is tested: the strategy, the tools, what each level covers, how to run every
suite locally, and where CI reports results and coverage. Everything here runs from a fresh
clone with Docker, `uv` and Node 24 (the version CI uses); nothing needs cloud access unless marked.

## Strategy

- **Every component tests itself.** Each service and pipeline is its own uv project (or npm
  project for the frontend) with its own `tests/`, run in its own CI job.
- **Fast and offline by default.** Unit and integration tests use fakes for the models, the
  database and the other services. They run in seconds with no GPU, no network and no secrets.
- **Real dependencies at the system level.** The Compose smoke test starts the whole stack
  (gateway, Postgres, mock LLM, frontend, monitoring) and drives real chat turns through it.
- **Safety cases are data.** Crisis, medication and camera wording lives in
  `services/api-gateway/tests/safety_cases.yaml`; every rule change adds cases, and CI must
  pass all of them.
- **Fail closed.** One required check, `CI summary`, fails if any job for a changed component
  did not pass. `main` needs that check green and one review.
- **Heavy checks are opt-in.** Tests that need a real model or GPU are skipped unless asked
  for, and documented below.

## Tools

| Tool | Used for |
|---|---|
| pytest | Python unit and integration tests (every service and pipeline) |
| pytest-cov | Coverage of runtime code in the three backend services, with a 70% gate (M4-20) |
| Vitest + Testing Library | Frontend unit and component tests (`services/frontend`) |
| Bash + curl + Docker Compose | System tests against the running stack (`infra/tests/test_compose_*.sh`) |
| Ruff | Lint and format for all Python (`ruff.toml`, M4-19) |
| ESLint, `tsc` | Frontend lint and type check |
| Locust | Load test (`tests/load`, M4-07; results in [`perf.md`](perf.md)) |
| Playwright | End-to-end patient-to-clinician smoke test (M4-05) |

## What each level covers

**Unit tests.** One function or class with fakes around it. Examples: the safety rules
(`services/api-gateway/tests/test_safety.py`), gating and fusion (`test_gating.py`,
`test_fusion.py`), the prompt builder (`test_prompt.py`), the SSE parser and API client in the
frontend (`src/lib/api/*.test.ts`), data cleaning in each pipeline.

**Integration tests.** Several parts of one service together, through its HTTP API, with fake
neighbours. Examples: a full chat turn through the gateway with fake CV and LLM
(`test_orchestration.py`, `test_chat.py`), clinician endpoints and ownership checks
(`test_clinician_endpoints.py`), auth (`test_auth_*.py`), fallbacks (`test_fallbacks.py`),
the database schema and seed in a real Postgres container (`services/db/tests/test_database.sh`),
and the shared contracts (`docs/contracts`: every example validates against its schema).

**System tests.** The whole stack in Compose, called like the browser calls it:

| Script | Checks |
|---|---|
| `infra/tests/test_compose_chat.sh` | An ordinary and a crisis chat turn are answered and saved in Postgres |
| `infra/tests/test_compose_fallbacks.sh` | With cv-service down or llm-service stopped, every turn still gets an answer |
| `infra/tests/test_compose_monitoring.sh` | Prometheus scrapes the gateway, the chat turns show up, and Grafana serves the dashboard (run it after `test_compose_chat.sh`) |

**Asset tests.** Deployment and CI files are checked as data: `infra/tests/test_stage_a_assets.py`,
`test_m3_14_assets.py`, `test_monitoring_assets.py`, `test_m4_21_one_command.py`,
`test_m4_19_linting.py`.

**End-to-end (browser).** M4-05 uses Playwright against a disposable local Compose stack: a seeded
patient signs in, consents to Chromium's synthetic camera stream, chats with the mock LLM, and a
seeded clinician opens the assigned-patient view. It never uses a physical camera, patient frames,
model downloads, or cloud services. To run it locally:

```bash
export MIRROR_DEMO_PASSWORD=local-only-e2e-password
export MIRROR_E2E_PASSWORD="$MIRROR_DEMO_PASSWORD"
docker compose -p mirror-e2e -f infra/compose.yml up --build --wait
(cd tests/e2e && npm ci && npx playwright install --with-deps chromium && npm test)
docker compose -p mirror-e2e -f infra/compose.yml down -v
```

## Run each suite locally

From the repository root unless stated.

### Python services and pipelines

Each folder below runs this base sequence, as in its CI job:

```bash
cd <folder>
uv sync --frozen --all-groups
uv run ruff check .
uv run pytest -v
```

`services/api-gateway`, `services/cv-service` and `services/llm-service` run the coverage
variant in CI instead of the last line; it enforces the 70% threshold:

```bash
uv run pytest -v --cov --cov-report=term-missing --cov-report=xml
```

| Folder | Notes |
|---|---|
| `services/api-gateway` | Coverage variant (70% gate) |
| `services/cv-service` | Coverage variant (70% gate); installs CPU-only PyTorch |
| `services/llm-service` | Coverage variant (70% gate); tests use the mock, no GPU |
| `services/_template` | Starting point for new services |
| `pipelines/data-preprocess`, `persona-data`, `iemocap-data` | Data stages |
| `pipelines/cv-train`, `cv-eval`, `fairness-audit` | Face model: train, evaluate, audit |
| `pipelines/llm-finetune` | LoRA fine-tune job |
| `pipelines/llm-eval/persona-checks`, `llm-eval/pairwise`, `modality-eval` | Evaluation harnesses |
| `docs/contracts` | Also run `uv run python validate.py` |

Coverage, the same way CI measures it:

```bash
cd services/api-gateway   # or cv-service, llm-service
uv run pytest --cov --cov-report=term-missing
```

Each service's `pyproject.toml` measures `app/` only and fails below 70%. The `Missing` column
lists the line numbers no test runs: this is the list of untested code per service.

### Frontend

```bash
cd services/frontend
npm ci
npm run lint && npm run typecheck && npm test && npm run build
```

### Repository-wide Python lint

```bash
uvx --from ruff==0.16.9 ruff check --config ruff.toml services pipelines
uvx --from ruff==0.16.9 ruff format --config ruff.toml --check services pipelines
```

### Database

```bash
bash services/db/tests/test_database.sh
```

Builds the database image, starts it, checks the 6 tables and the seed (2 clinicians, 5 patients,
each assigned to a clinician), and removes it.

### Asset tests

```bash
python3 infra/tests/test_stage_a_assets.py
python3 infra/tests/test_m3_14_assets.py
python3 infra/tests/test_m4_21_one_command.py
python3 infra/tests/test_m4_19_linting.py
uv run --no-project --with pyyaml==6.0.2 python infra/tests/test_monitoring_assets.py
```

`test_stage_a_assets.py` also validates the Caddyfile by running Caddy in Docker
(`caddy:2.10.2-alpine`); the prerequisite is Docker, not a local `caddy` binary.

### System tests (whole stack)

```bash
docker compose -f infra/compose.yml --profile monitoring up --build --wait --wait-timeout 300
curl -fsS http://localhost:8000/health && curl -fsS http://localhost:3000/health
bash infra/tests/test_compose_chat.sh
bash infra/tests/test_compose_fallbacks.sh
bash infra/tests/test_compose_monitoring.sh
docker compose -f infra/compose.yml --profile monitoring down -v
```

`down -v` also removes the database volume: the next start seeds a fresh demo database.

## Opt-in and manual tests

Not run in CI, on purpose:

| Test | Why it is opt-in | How to run |
|---|---|---|
| Text-emotion model speed (`services/api-gateway/tests/test_text_emotion_model.py`) | Downloads the ~330 MB model | `RUN_MODEL_TESTS=1 uv run pytest tests/test_text_emotion_model.py -q -s` |
| Persona checks against a real model (`pipelines/llm-eval/persona-checks`) | Needs llm-service in real mode on a GPU | See its README |
| Load test (`tests/load`, M4-07) | Needs the running stack; minutes long | See `tests/load/README.md` |
| DVC restore (`tests/m2_04_dvc_smoke.sh`) | Needs Google Cloud access to the data bucket | `bash tests/m2_04_dvc_smoke.sh` after `gcloud auth application-default login` |

## Where CI reports results

- **Workflow:** `.github/workflows/ci.yml` on every pull request to `main`. A first job detects
  which components changed; only their jobs run. A change under `.github/workflows/` runs them all.
- **Per component:** one job each, named after the component ("API gateway checks", "Frontend
  checks", ...), in the PR's Checks tab.
- **Coverage:** the three backend jobs print the per-file table in the job log and in the run's
  Summary page ("Coverage: services/..."). Below 70% the job fails. Path gating means a PR that
  changes no backend service shows no coverage table.
- **System tests:** "Compose stack smoke test"; on failure it prints every container's logs.
- **Browser acceptance:** "End-to-end patient to clinician smoke test" installs Chromium, starts
  the disposable `mirror-e2e` Compose stack, exercises the accepted patient-to-clinician flow, and
  removes the stack. It runs on every pull request to `main`.
- **Gate:** "CI summary" is the one required check. It fails if any job for a changed
  component did not succeed.

## Gaps

- Browser E2E is covered by the disposable Compose + Playwright M4-05 smoke test; it is a
  synthetic-camera, mock-LLM acceptance test rather than a real-model or paid-cloud validation.
- Pipelines and the frontend have no coverage gate yet; only the three backend services do.
  Vitest coverage for the frontend is not reported in CI.
- llm-service's coverage counts `app/` only, which is the mock. Real serving
  (`docker-entrypoint.sh` + vLLM) is not measured by any test.
- `infra/tests/test_m4_19_linting.py` and `tests/m2_04_dvc_smoke.sh` are not run by any CI job.
- What is still untested inside each service: the `Missing` column of the coverage table
  (see above); the full list is M5-12.
