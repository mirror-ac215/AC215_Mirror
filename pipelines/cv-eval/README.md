# Mirror CV evaluation (M2-08)

Reproducible, CPU-only evaluation of the inherited ViT-B/16 FER-2013 classifier. This job evaluates the DVC-restored held-out test split and emits aggregate metrics only; it never uploads frames, examples, model weights, or dataset artifacts.

## Baseline result

The verified M2-08 baseline run evaluated 7,178 FER-2013 v1 test examples with the documented grayscale→3-channel, 224×224, ImageNet-normalized transform: **macro-F1 0.64453**, passing the required **≥0.64** guard. W&B record: https://wandb.ai/mog941-harvard-university/mirror/runs/vqa4ulfz

## Local run

From the repository root, restore data with `dvc pull`, obtain the documented checkpoint through approved ADC, then run:

```bash
uv run --project pipelines/cv-eval mirror-cv-eval \
  --data-dir data/processed/fer2013/v1 \
  --checkpoint /secure/path/vit_b16_v3_best.pth \
  --output /secure/path/m2-08-report.json \
  --code-revision "$(git rev-parse HEAD)"
```

The evaluator builds its preprocessing from the DVC-produced `metadata/transform_spec.json`, and the report records that same transform identity. The report contains model/data/code/transform identity, aggregate metrics, and the inclusive macro-F1 regression decision. Add `--wandb-project mirror` only when you intentionally want to create a W&B run: it logs the evaluation identity, regression threshold/pass result, aggregate metrics, and runtime only. It does not upload frames, examples, reports, checkpoints, or artifacts. Keep reports, checkpoints, local DVC data, W&B credentials, and W&B working directories outside Git.

## M2-07 crop-alignment follow-up protocol

This is a **separate, evidence-gathering follow-up** to the M2-07 review. It does not change the online `cv-service` crop or resize behavior.

The paired experiment requires a non-sensitive, externally stored labelled manifest of live-like frames. Each row must contain `path`, `label`, and the independently verified Haar face box: `x`, `y`, `width`, `height`. Raw frames and the manifest remain outside Git, Docker contexts, reports, and W&B.

For every manifest row, evaluate the same checkpoint and label under both fixed variants:

1. current serving-style tight face crop followed by the documented 224x224 transform;
2. a 15% proportional crop margin, then grayscale 48x48 downscale, then the documented 224x224 transform.

The `mirror_cv_eval.crop_protocol` helpers validate the manifest box and produce the clipped proportional-margin crop. Keep the source face box fixed for both variants so the comparison isolates preprocessing rather than detection differences.

Do not change the serving default unless the paired aggregate report records macro-F1, per-class F1, top-1 accuracy, uncertainty-margin behavior, and CPU latency for both variants. The M2-08 FER-2013 regression evaluation is not a substitute: FER-2013 is already face-cropped and does not contain the original live-frame Haar boxes needed for this question.

## Validation

```bash
cd pipelines/cv-eval
uv sync --all-groups
uv lock --check
uv run ruff check .
uv run pytest -q
docker build -t mirror-cv-eval-ci .
```
