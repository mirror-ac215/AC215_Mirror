# Mirror CV training (M2-17)

Trains Mirror's facial-expression model: an ImageNet ViT-B/16, fully fine-tuned on FER-2013 to 7 emotions. This is the **baseline recipe** behind the model that `cv-service` serves today (`cv-vit-b16-v3`). It is now a containerised, tested, parameterised job instead of a notebook.

```
data/processed/fer2013/v1 (DVC) ──> mirror-cv-train ──> checkpoint (.pth) ──> GCS models/cv/<version>/
                                         │                                        │
                                   W&B (per epoch)                       cv-eval scores it · cv-service serves it
```

## Where the baseline came from
The baseline checkpoint `vit_b16_v3_best.pth` was trained by Mostafa in the CSCI E-25 project notebook (`facial_emotion_recognition_v3`), on a GPU. This job ports that notebook's code one-to-one:
- the same transforms, imbalance handling, loss, Mixup/CutMix and training loop;
- every setting moved into `params.yaml`;
- the inputs switched to our DVC-versioned dataset.

The inherited checkpoint is stored at `gs://mirror-ac215-data/models/cv/inherited-v3/vit_b16_v3_best.pth` (see `docs/artifacts.md`). Model weights are never committed to git.

## The recipe (`params.yaml`)
| | Setting | Why |
|---|---|---|
| Model | torchvision ViT-B/16, ImageNet weights; head = Dropout(0.5) + Linear(768, 7); all layers trainable | Best of 4 architectures tried (table below) |
| Input | grey 48×48 → 3 channels → 224×224, ImageNet mean/std | The same contract `cv-service` and `cv-eval` use |
| Augmentation | flip, affine (±10°, 5 % shift, 0.9–1.1 scale), colour jitter (0.4/0.4/0.2), Gaussian blur (p 0.5, σ 0.2–2.0), random erasing (p 0.25) | Blur imitates the softness of a live webcam |
| Imbalance | weighted sampler with √ rebalancing + focal-loss α from √ class weights | FER-2013 has 16× more *happy* than *disgust* |
| Loss | focal loss, γ = 2, label smoothing 0.1, soft labels from Mixup/CutMix (half of the batches) | Focuses learning on hard, rare classes |
| Optimiser | AdamW, lr 1e-5, weight decay 1e-4; ReduceLROnPlateau (×0.5, patience 2) | A small lr protects the pretrained features |
| Training | batch 32, 8 epochs, seed 42; keeps the best validation-accuracy epoch | |

## Results of the baseline
FER-2013 official test set, 7,178 images:

| Metric | Value |
|---|---|
| Top-1 accuracy | 0.666 |
| Top-2 accuracy | 0.838 |
| **Macro-F1** | **0.6445** |

✅ **Independently reproduced:** `pipelines/cv-eval` (M2-08) re-scored the same checkpoint in a container on the DVC test split and got **macro-F1 0.64453**, the same number ([W&B run](https://wandb.ai/mog941-harvard-university/mirror/runs/vqa4ulfz)). That is also the regression guard (≥ 0.64) every retrain must keep.

| Class | F1 (test) | | Architecture tried | Test macro-F1 |
|---|---|---|---|---|
| happy | 0.87 | | **ViT-B/16** | **0.645** |
| surprise | 0.78 | | EfficientNet-B0 | 0.626 |
| disgust | 0.64 | | MobileNetV3-Large | 0.607 |
| neutral | 0.63 | | CNN (from scratch) | 0.449 |
| angry | 0.56 | | | |
| sad | 0.53 | | | |
| fear | 0.50 | | | |

## Run it
Data first (from the repository root): `dvc pull` restores `data/processed/fer2013/v1`.

```bash
cd pipelines/cv-train
uv sync
# smoke run: 2 batches, no ImageNet download, CPU (about 30 s)
uv run mirror-cv-train --params params.yaml \
  --data-dir ../../data/processed/fer2013/v1 --output outputs/smoke.pth \
  --epochs 1 --max-batches 2 --no-pretrained
# full baseline recipe, with W&B tracking
uv run mirror-cv-train --params params.yaml \
  --data-dir ../../data/processed/fer2013/v1 --output outputs/vit_b16.pth --wandb-project mirror
```

With Docker (data and outputs mounted, never baked into the image):
```bash
docker build -t mirror-cv-train pipelines/cv-train
docker run --rm -v "$PWD/data:/data" -v "$PWD/outputs:/outputs" mirror-cv-train \
  --data-dir /data/processed/fer2013/v1 --output /outputs/vit_b16.pth
```

**Run on a GPU:** the lockfile pins the CPU build of PyTorch (for CI and laptops). On a CUDA machine, install the CUDA build of torch/torchvision in the environment first (the wheel index matching your driver, see pytorch.org). The job picks `cuda` automatically. 8 epochs of ViT-B/16 on ~23k images need a GPU: on a CPU it would take days.

**Output:** one checkpoint with the same keys as the inherited one (`model_state_dict`, `classes`, `best_epoch`, …, plus the `params` used), so `cv-eval` and `cv-service` load it unchanged. Upload a new version to `gs://mirror-ac215-data/models/cv/<version>/` and score it with `cv-eval` before serving it.

**Secrets:** none for training. `--wandb-project` needs `WANDB_API_KEY` in the environment (never in git). `dvc pull` needs Google application-default credentials.

## Data version and one known difference
Inputs are the DVC-tracked `data/processed/fer2013/v1` (`fer2013_preprocess` stage, hash in `dvc.lock`).
- **The test split** is FER-2013's official `test/` folder in both the notebook and the repo, which is why the two scores match.
- **The train/validation split differs:** the notebook used scikit-learn's stratified 80/20 split; `data-preprocess` uses its own per-class seeded shuffle (also 80/20, seed 42).
- A full re-run here should land near the baseline, but not byte-for-byte on the same epoch.

## Verification
```bash
uv run ruff check .
uv run pytest -v        # 10 tests: loss, class weights, sampler, Mixup/CutMix, transforms, head shape,
                        # a one-epoch end-to-end run on a tiny fake dataset, bad-label rejection
```

## Next iteration (MS3, M3-01)
FER-2013 is small and posed; MS1 feedback asked for more and more realistic data.
- Fine-tune on **Aff-Wild2** video frames (real faces in front of a camera, labels on every frame), **split by video, never by frame**.
- Add **FER+** labels (10 annotators per image) as soft targets.
- **Targets:** beat 0.6445 on the same test set, and lift the weakest classes (fear 0.50, sad 0.53).
- Every run is logged to W&B and scored by `cv-eval`. Our own labelled check-in sessions (M3-20) become the real-webcam validation set.

## M3-01: multi-source training (experimental)

> **Status: experimental.** This recipe produces candidate checkpoints only. It does not change the served model: cv-service still serves `cv-vit-b16-v3` until a candidate passes the final cv-eval and is handed to serving (below).

**Inputs (all must exist before a run):**

| Input | Where it comes from | Identity |
|---|---|---|
| FER-2013 v1 | `dvc pull` (`fer2013_preprocess` stage) | hash in `dvc.lock` |
| Aff-Wild2 v1 | built locally with `mirror-prepare-affwild2` (M3-18, `pipelines/data-preprocess`); Aff-Wild2 is licensed, so frames never leave the machine | source checksums + test-manifest hash in [`pipelines/cv-eval/provenance/m3-18-affwild2.json`](../cv-eval/provenance/m3-18-affwild2.json) |
| Starting model (v3) | `gs://mirror-ac215-data/models/cv/inherited-v3/vit_b16_v3_best.pth` | SHA-256 `f2e13fa8308b138714902c2d6995042572eef11192ffcc80a4fe137aa4815990` (343,278,498 bytes) |

Check the downloaded checkpoint before training: `(Get-FileHash -Algorithm SHA256 vit_b16_v3_best.pth).Hash` (PowerShell) or `sha256sum vit_b16_v3_best.pth`.

**Exact invocation** (from the repository root, dependencies as locked in `uv.lock`):

```bash
uv sync --frozen --project pipelines/cv-train
uv run --no-sync --project pipelines/cv-train mirror-cv-train \
  --params pipelines/cv-train/params_m3-01.yaml \
  --data-root data/processed \
  --init-checkpoint /secure/path/vit_b16_v3_best.pth \
  --output /secure/path/m3-01-<run>.pth \
  --wandb-project mirror
```

On a GPU machine, install the CUDA build of torch/torchvision into that environment after `uv sync` (the lockfile pins the CPU build), then keep `--no-sync` so uv doesn't swap it back. Run A (video only) adds `--set data.sources.fer2013.share=0`. With Docker, pass `--params params_m3-01.yaml` after the image name: the entrypoint already passes `--params params.yaml`, and the last one wins.

**Output identity:** one local `.pth` with the same keys as the baseline, plus the exact `params` and overrides used (also logged to W&B). `report_test: false`, so no held-out test set is scored during training. **Nothing is published from this step.**

**From candidate to served model** (in this order):
1. Score the candidate once with `pipelines/cv-eval` on the three held-out test sets (FER-2013 guard ≥ 0.64, Aff-Wild2 test videos, FER+ test), with `--model-version` set to the candidate's name and a W&B run each.
2. Record a provenance file per result (like `pipelines/cv-eval/provenance/`).
3. Upload the checkpoint to `gs://mirror-ac215-data/models/cv/<version>/` and record its SHA-256 in `docs/artifacts.md`.
4. Serving handoff to Owen (cv-service owner): the new `MODEL_OBJECT` and `MODEL_VERSION`, changed together in one reviewed config change.
