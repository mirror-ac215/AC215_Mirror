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
uv run pytest -v        # 19 tests: loss, class weights, samplers, Mixup/CutMix, soft labels, schedules,
                        # weight averaging, layer decay, end-to-end runs on tiny fake datasets
```

## M3-01: v4, retrained on real video (MS3)
> **Status: experimental.** v4 is published to GCS but not served: cv-service still serves `cv-vit-b16-v3` until the serving handoff (M3-03/M3-10). The scores below are candidate results, not an accepted serving decision.

FER-2013 is small and posed; MS1 feedback asked for more realistic data. **v4** (`cv-vit-b16-v4`) is v3 fine-tuned on **Aff-Wild2** video frames together with **FER+** photos, whose labels are the vote shares of 10 annotators (soft labels). Recipe: `params_m3-01.yaml` plus the run's `--set` options (recorded in W&B and inside the checkpoint).

```bash
# v4 (run C3), from pipelines/cv-train; data built with mirror-prepare-affwild2 and mirror-prepare-ferplus
uv run --no-sync mirror-cv-train --params params_m3-01.yaml --data-root ../../data/processed \
  --init-checkpoint /secure/path/vit_b16_v3_best.pth --output /secure/path/vit_b16_v4.pth \
  --set data.sources.fer2013.dir=ferplus/v2 --set data.sources.fer2013.soft_labels=true \
  --set scheduler.name=cosine --set training.epochs=8 --set training.ema_decay=0.999 --wandb-project mirror
```

**Final scores, held-out test sets, scored once with `cv-eval`** (artifact `gs://mirror-ac215-data/models/cv/v4/vit_b16_v4.pth`):

| Test set | v3 | **v4** | W&B |
|---|---|---|---|
| Aff-Wild2 test (official validation videos, 45 people, real video) | 0.260 | **0.337** | [run](https://wandb.ai/mog941-harvard-university/mirror/runs/u48hqxhw) |
| FER+ test (10-annotator labels; photo guard >= 0.609, see D-005) | 0.609 | **0.720** | [run](https://wandb.ai/mog941-harvard-university/mirror/runs/ggxg1qqi) |
| FER-2013 test (single-annotator labels; former guard) | 0.645 | 0.588 | [run](https://wandb.ai/mog941-harvard-university/mirror/runs/11d3q8x3) |

v4 learned what 10 people see rather than what one labeller wrote, so it agrees less with FER-2013's labels (M3-18 showed they disagree with the crowd on about a third of the photos). Aff-Wild2 test per class: disgust 0.01 -> 0.36, angry 0.07 -> 0.25, neutral 0.35 -> 0.46, happy 0.55 -> 0.61; fear 0.19 -> 0.05 and sad 0.35 -> 0.30 (3 and 9 test videos).

**Experiments** (one change at a time; model chosen on Aff-Wild2 *validation*, 36 videos of our own split, never on test):

| Run | Change | Aff-Wild2 val | FER+ val | W&B |
|---|---|---|---|---|
| v3 | inherited | 0.191 | 0.602 | |
| A | Aff-Wild2 only, from v3 | 0.301 | forgets photos | [hz8v26sr](https://wandb.ai/mog941-harvard-university/mirror/runs/hz8v26sr) |
| B | + FER-2013 (50/50) | 0.297 | 0.617 | [0wo6u88k](https://wandb.ai/mog941-harvard-university/mirror/runs/0wo6u88k) |
| C | FER+ soft labels instead | 0.314 | 0.704 | [uufehscw](https://wandb.ai/mog941-harvard-university/mirror/runs/uufehscw) |
| C2 | + cosine schedule, 8 epochs | 0.298 | 0.707 | [h8erb3g6](https://wandb.ai/mog941-harvard-university/mirror/runs/h8erb3g6) |
| **C3 = v4** | **+ weight averaging (EMA)** | **0.290** | **0.711** | [lgeo815r](https://wandb.ai/mog941-harvard-university/mirror/runs/lgeo815r) |
| C4 | + fully balanced sampling | 0.275 | 0.699 | [19pov8rq](https://wandb.ai/mog941-harvard-university/mirror/runs/19pov8rq) |
| C5 | + layer-wise lr decay | 0.278 | 0.699 | [afby6xhl](https://wandb.ai/mog941-harvard-university/mirror/runs/afby6xhl) |
| D | ImageNet start, Aff-Wild2 only | 0.240 | none | [e6610uxr](https://wandb.ai/mog941-harvard-university/mirror/runs/e6610uxr) |
| HSEmotion | AffectNet-trained EfficientNet-B2 ([HSEmotion](https://github.com/av-savchenko/hsemotion)), no training | 0.314 | | |
| H1 | C3 recipe from HSEmotion, lr 1e-4 | 0.324 (epoch 1) | 0.651 | [uo8vfsjd](https://wandb.ai/mog941-harvard-university/mirror/runs/uo8vfsjd) |
| H2 | H1 with lr 2e-5 | 0.319 (epoch 1) | 0.614 | [72v5gxax](https://wandb.ai/mog941-harvard-university/mirror/runs/72v5gxax) |
| H3 | H1 training only the classifier (frozen features) | 0.316 (epoch 1) | ~0.62 | [b86ac03q](https://wandb.ai/mog941-harvard-university/mirror/runs/b86ac03q) |

Why C3: within the noise of the best video score, the best FER+ score, and the steadiest curve (last three epochs within 0.004), so the result does not depend on a lucky epoch. Mirror-image averaging at test time gave no gain.

**What we learned**
- Starting from v3 helps: the same video-only training from ImageNet (D) is about 20 % worse and overfits (train 0.91 vs val 0.47 accuracy).
- Mixing in photos costs no video quality and stops the model forgetting them (A vs B).
- The limit is data, not settings: on video, fear is read as surprise and sadness as neutral in every run, and balancing (C4) or freezing (C5) did not change it. Aff-Wild2 has only 16-28 training people per rare emotion. More people per emotion (RAF-DB, AffectNet, our consented M3-20 sessions) is the next lever, plus face alignment in `cv-service` to match Aff-Wild2's aligned crops.
- A model pre-trained on ~400k AffectNet faces (HSEmotion) reaches the same ceiling: used as-is it scores 0.314, and every way of training it on our data (H1-H3) peaks at the first epoch within 0.01 of that, with lower photo scores than v4. It is better at fear, worse at anger. v4 stays the model: equal on video, better on photos, a drop-in for cv-service, and our own licence (HSEmotion weights are research-only). The EfficientNet support (`model.architecture`, `model.global_pool`, `model.train_only_head`) stays in cv-train, off by default, for when more data arrives. The HSEmotion start checkpoint is rebuilt from its ONNX release with `scripts/convert_hsemotion.py` (no pickle; output identical to the original).
- v4 is published but **not yet served**: switching `cv-service` is integration work (M3-03/M3-10).

**Caveats**
- **Near-duplicate photos:** FER-2013 has some near-duplicate faces across its Training and PublicTest/PrivateTest parts. Training on FER+ train therefore lifts the FER+ test score a little through those. v3 was trained on the same Training photos, so the v3 vs v4 comparison is fair; the Aff-Wild2 test score (separate people) is not affected.
- **Weight decay on every parameter:** AdamW applies `weight_decay` (1e-4) to all weights, including biases, LayerNorm weights, `class_token` and `pos_embedding`; the usual ViT recipe exempts those. The effect is likely small over 6-8 epochs from v3, and v4 was trained this way, so it is noted rather than changed.

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

**Epoch length:** one M3-01 epoch draws as many samples as all sources' training rows together (after `every_nth`), split between the sources by `share`. So "6 epochs" here is not the same amount of training as the baseline's 8 epochs over FER-2013 alone; compare runs by W&B step or samples seen, not by epoch number.

**Output identity:** one local `.pth` with the same keys as the baseline, plus the exact `params` and overrides used (also logged to W&B). `report_test: false`, so no held-out test set is scored during training. **Nothing is published from this step.**

**From candidate to served model** (in this order):
1. Score the candidate once with `pipelines/cv-eval` on the three held-out test sets (FER-2013 guard ≥ 0.64, Aff-Wild2 test videos, FER+ test), with `--model-version` set to the candidate's name and a W&B run each.
2. Record a provenance file per result (like `pipelines/cv-eval/provenance/`).
3. Upload the checkpoint to `gs://mirror-ac215-data/models/cv/<version>/` and record its SHA-256 in `docs/artifacts.md`.
4. Serving handoff to Owen (cv-service owner): the new `MODEL_OBJECT` and `MODEL_VERSION`, changed together in one reviewed config change.
