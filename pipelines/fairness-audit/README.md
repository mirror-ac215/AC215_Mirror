# Mirror fairness audit (M3-02)

Does the CV model behave differently for people of different race, gender or age? This job runs the served pipeline (Haar face detection, then the ViT-B/16 expression model, then the gateway's gate) on every photo of the FairFace validation set and compares the groups. The report opens with the largest gap, stated in one sentence; the CV model card (M4-10) cites it.

## What it measures

FairFace (Karkkainen & Joo, WACV 2021; CC BY 4.0) has 10,954 validation photos, balanced across 7 race groups, 2 genders and 9 age groups. It has **no expression labels**: the audit shows how differently the model *behaves* per group, not how *accurate* it is. Accuracy gaps need RAF-DB, which has attribute and expression labels; it was requested on Sep 28 and never granted (board M1-05, M3-19).

Per group:

| Measure | Meaning | Why it matters |
|---|---|---|
| `face_found` | Haar finds a face (cv-service step 1) | no face -> Mirror ignores the camera for that person |
| `gate_ok` | face found **and** the gate passes | the share of readings the gateway would actually use |
| `gate_ok_if_face` | gate passes, among photos with a face | the model alone, without the detector |
| `confidence` | mean top probability | a less confident model is gated out more often |
| `share_<emotion>` | share of photos read as each emotion | e.g. one group read as angry or sad more often |
| `share_negative` | angry + disgust + fear + sad | the readings that matter most to clinicians |
| `share_happy` | share read as happy, shown next to the negative share | a group seldom read as happy is a gap as well |

The **gap** for a measure is the highest group minus the lowest, among groups with at least `min_group_size` photos. "Beyond noise" means the two groups' 95% intervals (Wilson for shares) do not overlap.

## Choices (params.yaml)

- **Gate on a photo.** A photo is one steady frame: stability is always 1.0, and only the gateway's top-probability (0.45) and margin (0.05) rules apply. A test keeps these equal to the gateway defaults in `services/api-gateway/app/config.py`.
- **No face found.** cv-service would answer "no face"; the audit records that and still scores the whole photo. The model's own behaviour can therefore be compared on every photo.
- **Children.** Ages 0-2 and 3-9 are excluded from the gaps (Mirror's patients are teenagers and adults) and reported in their own table.
- **Model.** `cv-vit-b16-v4` (`docs/artifacts.md`); the report refuses predictions from another model version.

## Code

| File | What it does |
|---|---|
| `src/mirror_fairness_audit/fairface.py` | reads `fairface_label_val.csv` and rejects unknown group names |
| `src/mirror_fairness_audit/score.py` | the slow step: cv-service's detection and preprocessing, the model, one CSV row of probabilities per photo (no images written) |
| `src/mirror_fairness_audit/audit.py` | the fast step: per-group measures, 95% intervals, gaps |
| `src/mirror_fairness_audit/report.py` | `report.json` (for the model card) and `report.md`, headline first |
| `src/mirror_fairness_audit/cli.py` | `score` and `report` commands |
| `tests/` | 20 tests with invented predictions and a stand-in model: no FairFace or checkpoint needed |

## Run it (Colab, about 10 minutes on a T4)

Sign in to Colab with the account that is Editor on `mirror-ac215`, select a GPU runtime, and run:

```python
# 1. Code. --no-deps keeps Colab's own CUDA torch.
!git clone -q https://github.com/mirror-ac215/AC215_Mirror.git
%cd /content/AC215_Mirror
!git switch -q jl/M3-02-fairness-audit
!uv pip install --system --no-deps -e pipelines/fairness-audit

# 2. The v4 checkpoint
from google.colab import auth
auth.authenticate_user()
!gcloud storage cp gs://mirror-ac215-data/models/cv/v4/vit_b16_v4.pth /content/

# 3. FairFace validation (padding 0.25) as images + the official label file
import csv, os
from datasets import load_dataset
ds = load_dataset("HuggingFaceM4/FairFace", "0.25", split="validation")
os.makedirs("/content/fairface/val", exist_ok=True)
with open("/content/fairface/fairface_label_val.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["file", "age", "gender", "race", "service_test"])
    names = {k: ds.features[k].int2str for k in ("age", "gender", "race")}
    for i, ex in enumerate(ds):
        ex["image"].convert("RGB").save(f"/content/fairface/val/{i}.jpg", quality=95)
        w.writerow([f"val/{i}.jpg", names["age"](ex["age"]), names["gender"](ex["gender"]),
                    names["race"](ex["race"]), ex["service_test"]])

# 4. Score (slow) and report (fast)
!mirror-fairness-audit --params pipelines/fairness-audit/params.yaml score \
  --images-dir /content/fairface --labels /content/fairface/fairface_label_val.csv \
  --checkpoint /content/vit_b16_v4.pth --output /content/out/predictions.csv \
  --device cuda --code-revision $(git rev-parse HEAD)
!mirror-fairness-audit --params pipelines/fairness-audit/params.yaml report \
  --predictions /content/out/predictions.csv --output-dir /content/out/report
```

Download `report.md`, `report.json` and `predictions.meta.json` from `/content/out/`, then disconnect the runtime. The two report files hold aggregate numbers only and are committed under `results/fairface-v4/`; `predictions.csv` stays out of git.

Locally (CPU, slower): `uv sync` in this folder, then the same two commands with `uv run` and without `--device cuda`.

## Checks

```bash
cd pipelines/fairness-audit
uv sync --all-groups && uv run ruff check . && uv run pytest -q
docker build -t mirror-fairness-audit-ci .
```

## Results

To be filled in after the first run: the headline sentence, the key-gaps table, and the provenance (checkpoint, labels and predictions sha256, code commit).

## Not in this PR

- Accuracy gaps by group (RAF-DB, if access is granted; MS5 at the earliest).
- Skin tone (FairFace labels race, not skin tone) and webcam conditions such as lighting.
