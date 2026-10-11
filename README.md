# Mirror

An emotion-aware conversational companion with a clinician view.
AC215 (Harvard, Fall 2026) course project. **A prototype, not a clinical product.**

A patient chats with a supportive persona. With consent, their webcam gives a facial-expression signal and their text gives a tone signal. Both are smoothed, gated and fused into one short, uncertainty-labelled context note per message, and that note shapes the reply. A deterministic text-only safety check runs before the model: if it fires, the app shows crisis resources (988) and flags the conversation for the clinician. The clinician dashboard shows affect trends between sessions.

Team: Mostafa Galal, Owen Chong, Julie Lander, Samuel Tanner.

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

The local stack (frontend, api-gateway, db) runs with Docker Compose. Details,
configuration and troubleshooting are in [`infra/README.md`](infra/README.md).

```bash
git clone https://github.com/mirror-ac215/mirror.git
cd mirror
cp infra/.env.example infra/.env   # fill in the two values
docker compose -f infra/compose.yml up --build -d
```

Then open http://localhost:3000 (app) and http://localhost:8000/docs (gateway API).
`llm-service` and `cv-service` join the stack when their PRs merge.

## Data setup with DVC

Raw datasets are versioned with DVC, while the actual content is stored in the team's GCS bucket. Raw data is never committed to Git.

After cloning, authenticate once for DVC's GCS backend, then retrieve the tracked dataset version:

```bash
gcloud auth application-default login
dvc pull
```

`dvc pull` restores these required raw inputs:

```text
data/raw/fer2013/archive.zip
data/raw/persona/jbp_clean_full.csv
data/raw/persona/jbp_train.csv
data/raw/persona/jbp_val.csv
data/raw/persona/jbp_test.csv
```

The DVC remote is `mirror_gcs` at `gs://mirror-ac215-data/dvc`. Do not run `git add data/`; commit only the DVC configuration and `.dvc` metadata files.

## How we work

- **One task, one branch, one pull request.** Name the branch `<initials>/<task-id>-short-name`, for example `mg/M1-03-repo-skeleton`.
- **Merging into `main`.** Every pull request needs one approving review. No direct pushes.
- **Environments.** Every Python component is its own uv project: `pyproject.toml` and `uv.lock` are committed, and `.venv/` is not.
- **What stays out of git.** Secrets, raw data and model weights never go in. Data is tracked with DVC and models are stored in GCS.
