# Mirror llm-finetune (M3-09)

## Purpose

Retrains Mirror's persona **LoRA adapter** for `Qwen/Qwen2.5-3B-Instruct` on the filtered persona pairs from M2-09, as a **Vertex AI custom job** (serverless GPU training, MS3). The adapter is a swappable style layer: the public-figure data is only a stand-in for a clinician's own consented material, disclosed as AI.

| | |
|---|---|
| Input | `data/processed/persona/v1/{train,val,test}.csv` (`pair_id, prompt, response`) |
| Output | `gs://mirror-ac215-data/models/llm/adapter-v2/`: adapter weights, tokenizer, `mirror_adapter.json` |
| Tracking | one W&B run per training run (project `mirror`), named after the adapter |

## How it trains

- **QLoRA:** the 3B base model is loaded in 4-bit (NF4); only the LoRA weights (r=32, alpha=64, dropout 0.05, the same shape as adapter-v1) are trained.
- **Loss on Mirror's replies only:** each example is `system + patient message -> reply` (TRL prompt-completion format); the system prompt and the patient's words are never learned as output.
- **Mirror's own system prompt** (`params.yaml`), which never names the source person, unlike the old notebook prompt.
- **Best epoch kept:** validation loss is computed every epoch; the lowest wins.
- **Reproducible and versioned:** the base model is pinned to a commit (`base_model.revision`), and `mirror_adapter.json` records the base revision, data version and sha256, git SHA, LoRA and training parameters, and the W&B run. An existing adapter folder is never overwritten; bump `output.adapter_name` instead.

## Run it

```bash
# 0. Data (from the repo root)
dvc pull raw-persona.dvc && dvc repro persona_clean
gcloud storage cp -r data/processed/persona/v1 gs://mirror-ac215-data/data/processed/persona/v1

# 1. Pin the base model: set base_model.revision in params.yaml to the latest
#    40-character commit on huggingface.co/Qwen/Qwen2.5-3B-Instruct ("Files and versions").

# 2. Checks (no GPU needed)
cd pipelines/llm-finetune && uv sync --all-groups && uv run ruff check . && uv run pytest -q

# 3. Build and push the GPU image, then set vertex.image_uri to it
IMAGE=us-central1-docker.pkg.dev/mirror-ac215/<repo>/llm-finetune:$(git rev-parse --short HEAD)
docker build --platform linux/amd64 --target train -t "$IMAGE" . && docker push "$IMAGE"

# 4. Submit (dry run first: prints the job spec with secrets masked)
export WANDB_API_KEY=... GIT_SHA=$(git rev-parse HEAD)
uv run --extra vertex mirror-llm-finetune submit \
  --data-uri gs://mirror-ac215-data/data/processed/persona/v1 --dry-run
uv run --extra vertex mirror-llm-finetune submit \
  --data-uri gs://mirror-ac215-data/data/processed/persona/v1
```

Inside the job, `gs://bucket/...` paths are read and written as `/gcs/bucket/...` (Cloud Storage FUSE); the training code therefore only sees ordinary files.

On a GPU machine without Vertex: `uv sync --extra train && uv run mirror-llm-finetune train`.

## Environment and secrets

| Variable | Needed for | Where it comes from |
|---|---|---|
| `WANDB_API_KEY` | W&B logging | `secrets/` instructions; passed to the job at submit time, never committed |
| `GIT_SHA` | recorded in `mirror_adapter.json` | `git rev-parse HEAD` |
| `HF_TOKEN` | optional (the base model is public) | your Hugging Face account |
| GCP auth | submit and GCS access | `gcloud auth application-default login` |

## Before the first run (team decisions)

- The Vertex AI API is enabled on `mirror-ac215`, with **L4 quota** in `us-central1` (alternatively, change `vertex.region`, or use a T4 with `compute_dtype: float16`).
- An Artifact Registry repository exists for the image (shared with M3-14).
- Cost: one L4 GPU per run, billed only while the job runs; the job stops when training ends.

## Not in this PR

- The 30 identity probe prompts and the distress-scenario test set, run right after training (M3-09 definition of done): next PR, in `pipelines/llm-eval`.
- Serving adapter-v2 in llm-service and the `docs/artifacts.md` row: after the first successful run.
