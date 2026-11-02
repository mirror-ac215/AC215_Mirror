# Artifacts

What we store in the team bucket `gs://mirror-ac215-data/`, where each file came from, and how good it is.

| File (GCS path) | What it is | Size | Source | Metrics |
|---|---|---|---|---|
| `models/cv/inherited-v3/vit_b16_v3_best.pth` | ViT-B/16, 7-class facial expression, main model | 327 MB | CSCI E-25, `facial_emotion_recognition_v3_Mostafa_Galal.ipynb` | test: 66.6% top-1, 83.8% top-2, 0.645 macro-F1 |
| `models/cv/v4/vit_b16_v4.pth` | ViT-B/16, 7-class facial expression, v4 (v3 fine-tuned on Aff-Wild2 + FER+ soft labels, M3-01) | 327 MB | `pipelines/cv-train`, `params_m3-01.yaml` run C3 | test: Aff-Wild2 0.337, FER+ 0.720, FER-2013 0.588 macro-F1 (D-005) |
| `models/cv/inherited-v3/efficientnet_b0_v3.pth` | EfficientNet-B0, backup / lighter CV model | 16 MB | same notebook | test: 65.2% top-1, 0.626 macro-F1 |
| `models/cv/inherited-v3/mobilenet_v3_large_best.pth` | MobileNetV3-Large, lightest CV model | 16 MB | CSCI E-25, `01_model_training_and_evaluation.ipynb` | best validation accuracy 60.6% |
| `models/cv/inherited-v3/per_class_thresholds.npy` | Per-class decision thresholds for the CV models | <1 KB | v3 notebook | n/a |
| `models/llm/adapter-v1/` | LoRA **adapter only** (not the full model) for `Qwen/Qwen2.5-3B-Instruct`; the base model (~6 GB) is pulled from Hugging Face by name at load time. Key files: `adapter_model.safetensors` (trained weights), `adapter_config.json` (base model + r=32, alpha=64, dropout 0.05), tokenizer + chat template | 240 MB | CSCI E-222, `Jordan_Peterson_Clone.ipynb` (masked, best checkpoint) | to be evaluated in MS3/MS4 |
| `data/raw/fer2013/archive.zip` | FER-2013 dataset | 60 MB | public (Kaggle) | 7 classes, 48x48 grayscale |
| `data/raw/persona/*.csv` | Persona prompt/response pairs | <1 MB | extracted from public long-form interviews | 380 pairs: 304 train / 38 val / 38 test |

Everything lives in `gs://mirror-ac215-data/`. Download with `gcloud storage cp gs://mirror-ac215-data/<path> .` (requires project access).

## Processed FER-2013 v1 — merged preprocessing pipeline

The processed-data release is `data/processed/fer2013/v1/` in the team bucket.
Its preprocessing code, manifests, deterministic split, and publication workflow
were accepted in M2-06 (PR #24) and are available from `main`.

Its output layout is intentionally inspectable:

```text
images/{train,val,test}/<class>/<image>.png
manifests/{train,val,test}.csv
reports/data_report.json
metadata/transform_spec.json
```

The preprocessing workflow distinguishes `dvc repro` (local, reproducible
materialization) from an explicit publish operation to the versioned GCS
prefix. This prevents an ordinary local rebuild from mutating shared storage.
