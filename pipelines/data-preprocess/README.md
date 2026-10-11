# Mirror FER-2013 preprocessing (M2-06)

## Purpose

Build a reproducible FER-2013 v1 dataset for later CV training and evaluation. The job validates the DVC-restored archive, preserves validated 48×48 grayscale PNGs, stratifies the supplied `train/` set into 80% train and 20% validation using seed 42, and preserves the supplied `test/` set.

## Model contract

Stored images remain grayscale 48×48 PNGs. Training and inference loaders, not this dataset, apply the inherited `vit_b16_v3_best.pth` transform: grayscale to three channels, resize to 224×224, `ToTensor()` `[0,1]`, then ImageNet mean `(0.485, 0.456, 0.406)` and standard deviation `(0.229, 0.224, 0.225)`. Training-only augmentation is excluded.

Class order: `angry`, `disgust`, `fear`, `happy`, `neutral`, `sad`, `surprise`.

## Run

From the repository root, first materialise the local, DVC-declared output without any cloud side effect:

```bash
dvc pull
dvc repro fer2013_preprocess
```

To publish that already-validated version explicitly, authenticate with Google Application Default Credentials and run:

```bash
gcloud auth application-default login
PYTHONPATH=pipelines/data-preprocess/src \
  uv run --project pipelines/data-preprocess mirror-preprocess \
  --params pipelines/data-preprocess/params.yaml \
  --publish
```

`--publish` uploads to `gs://mirror-ac215-data/data/processed/fer2013/v1/` with the bounded `output.publish_workers` setting (32). It is deliberately separate from `dvc repro` so routine reproducibility checks cannot change shared GCS state.

## Outputs

- `images/{train,val,test}/<class>/<image>.png`
- `manifests/{train,val,test}.csv` with `path,label,split`
- `reports/data_report.json` with input validity and class balance
- `metadata/transform_spec.json` with the load-time transform contract

## Verification

```bash
uv run pytest -v
uv run ruff check .
uv lock --check
```

Running unchanged inputs and `params.yaml` twice must produce identical manifest hashes.
