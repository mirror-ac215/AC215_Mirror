# Mirror CV service

CPU-only facial-expression inference for Mirror's internal gateway boundary.

```text
GET  /health
GET  /metrics
POST /predict        (multipart field: image, JPEG only)
POST /predict_batch  (multipart field: images, up to MAX_BATCH_SIZE JPEGs)
```

`/predict` detects a face before classification. If no face is detected, it returns the no-signal contract response (`face_found=false`, empty `probs`/`top2`, null `margin`/`uncertain`). Detected faces use the inherited 7-class ViT-B/16 model and return `angry`, `disgust`, `fear`, `happy`, `neutral`, `sad`, and `surprise` probabilities. Input preprocessing is grayscale, expanded back to RGB, resized to 224×224, then ImageNet-normalized.

`/predict_batch` runs the same per-image contract across a bounded list of frames (default `MAX_BATCH_SIZE=8`) and returns `{"predictions": [...]}` in request order; a batch over the limit is rejected with HTTP 422 before any image is read. Frames are not persisted in either endpoint.

The immutable public contract is [`docs/contracts/cv-service.openapi.yaml`](../../docs/contracts/cv-service.openapi.yaml). `/metrics` is an operational JSON endpoint; it is not part of that public prediction contract.

## Model startup and credentials

At application startup the service downloads exactly this configured artifact with Application Default Credentials (ADC), saves it only to `MODEL_CACHE_DIR`, then loads it on CPU:

```text
gs://mirror-ac215-data/models/cv/inherited-v3/vit_b16_v3_best.pth
```

Defaults are in `.env.example`. The checkpoint, credentials, cached model, and frames must never be added to Git or a Docker build context. The service logs one JSON record per HTTP request with `request_id`, path, status, and latency; it returns the ID in `X-Request-ID`.

`UNCERTAIN_MARGIN` defaults to `0.1` and must be between `0.0` and `1.0`. A detected face is marked `uncertain` when its top-1 minus top-2 probability margin is below this setting. This keeps the deployed default stable while allowing the M3 gate to be calibrated without editing service code.

## Serving/training boundary: approved model version

Mostafa owns model selection, training, and the artifact that becomes `MODEL_OBJECT`; Owen owns this service, which only loads whatever artifact is configured and serves it safely. `MODEL_VERSION_TAG_OBJECT` is an optional, serving-only convenience: if set, it points at a small GCS text object (not a model weights file) naming the version Mostafa has approved, and `/health`/`/metrics` report that value. It never changes which artifact is downloaded — `MODEL_OBJECT` is still set explicitly by Owen's configuration, so a version tag can never cause an unreviewed artifact to be served. A missing or malformed tag object fails startup loudly (`/health` stays `503`) rather than silently falling back to a guessed version.


## M2-08 baseline evaluation

The inherited ViT-B/16 checkpoint was evaluated on the DVC-restored FER-2013 v1 test split (7,178 examples) using the documented grayscale-to-RGB, 224×224, ImageNet-normalized transform. It achieved **0.64453 macro-F1** and passed the required `>= 0.64` regression guard. Aggregate metrics and evaluation identity are recorded in the verified [Weights & Biases run](https://wandb.ai/mog941-harvard-university/mirror/runs/vqa4ulfz). No raw frames, image examples, model weights, or dataset artifacts were uploaded.

No model download is performed by tests or Docker build. A missing/invalid checkpoint leaves `/health` at HTTP 503 rather than serving fake predictions.

## Local unit validation (no cloud access)

```bash
cd services/cv-service
uv sync --all-groups
uv lock --check
uv run ruff check .
uv run pytest -v
```

Tests use generated JPEGs and fake GCS/model clients; they do not access raw frames or GCS.

## Real model container

On an approved machine with read-only access to the documented GCS object, build and run with an ADC credential file mounted read-only:

```bash
docker build --tag mirror-cv-service:local .
docker run --rm -p 18001:8001 \
  -e GOOGLE_APPLICATION_CREDENTIALS=/var/secrets/google/adc.json \
  -v "$GOOGLE_APPLICATION_CREDENTIALS:/var/secrets/google/adc.json:ro" \
  mirror-cv-service:local
curl -fsS http://localhost:18001/health
```

This task did not download or validate the real checkpoint. Do not use a service-account key from the repository; use the approved ADC flow or a separately managed credential mount.

## Compose profile

The default `docker compose -f infra/compose.yml up --build` stack deliberately excludes this service, so its ordinary CI smoke test does not need cloud credentials. Start CV explicitly only after exporting a local ADC file path:

```bash
export CV_GOOGLE_APPLICATION_CREDENTIALS="$GOOGLE_APPLICATION_CREDENTIALS"
docker compose -f infra/compose.yml --profile cv up --build cv-service
```

`cv-service` uses port 8001 and the Compose profile mounts `CV_GOOGLE_APPLICATION_CREDENTIALS` read-only. If the checkpoint cannot be fetched or is incompatible, inspect service logs and `/health`; do not replace it with a model artifact copied into the image.
