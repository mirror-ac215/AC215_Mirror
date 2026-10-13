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

The report contains model/data/code/transform identity, aggregate metrics, and the inclusive macro-F1 regression decision. Keep reports, checkpoints, local DVC data, W&B credentials, and W&B working directories outside Git.

## Validation

```bash
cd pipelines/cv-eval
uv sync --all-groups
uv lock --check
uv run ruff check .
uv run pytest -q
docker build -t mirror-cv-eval-ci .
```
