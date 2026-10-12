# Mirror persona-data cleaning (M2-09)

## Purpose

Turns the raw persona prompt/response pairs into a clean, versioned dataset for
the LoRA retrain (M3-09). The persona must never claim to be a doctor,
psychologist, professor or a real person, so any response that makes an
identity or credential claim is removed, not rewritten. Every removal is
recorded with its reason.

Steps, in this order:

1. **Read** `data/raw/persona/jbp_clean_full.csv` (restored by DVC): columns
   `question` and `answer`. The old `jbp_train/val/test.csv` split files hold
   the same rows and are ignored. The `formatted` column (the old training
   prompt, which names the real person) is dropped; M3-09 builds Mirror's own
   prompt.
2. **Normalise** whitespace (wording and case are kept).
3. **Drop** empty pairs, responses shorter than 12 or longer than 4,000 characters.
4. **Filter identity/credential claims** with the regex list in `params.yaml`
   (`identity_filters`), e.g. "I am Dr…", "as a clinical psychologist",
   "my patients", and the source person's name, employer, books and family.
   Each rule has an id, so the report says which rule fired.
5. **Dedupe** exact duplicates (ignoring case and spacing).
6. **Split** 80/10/10 into train/val/test with seed 215.

## Inputs and outputs

| | Path | In git? |
|---|---|---|
| Input | `data/raw/persona/jbp_clean_full.csv` (`question`, `answer`) | No, DVC (`raw-persona.dvc`) |
| Output | `data/processed/persona/v1/{train,val,test}.csv` (`pair_id, prompt, response`) | No, DVC |
| Output | `data/processed/persona/v1/removed.csv` (source row, reason, first 80 chars) | No, DVC |
| Output | `data/processed/persona/v1/report.json` (before/after counts, split hashes) | No, DVC |

## Run (fresh clone)

From the repository root:

```bash
gcloud auth application-default login     # once; needs access to the mirror-ac215 project
dvc pull raw-persona.dvc                  # fetch the raw pairs
dvc repro persona_clean                   # run this stage
dvc push                                  # share the new processed version
```

Without DVC (same result):

```bash
cd pipelines/persona-data
uv sync
uv run mirror-persona-data --params params.yaml \
  --input ../../data/raw/persona --output ../../data/processed/persona/v1
```

With Docker (data mounted, never baked into the image):

```bash
docker build -t mirror-persona-data pipelines/persona-data
docker run --rm -v "$PWD/data:/app/data" mirror-persona-data
```

**Env vars / secrets:** none for the job itself. `dvc pull`/`dvc push` need
Google Application Default Credentials (see `secrets/README.md`).

## Results

<!-- TODO(Julie): paste report.json numbers after the first real run -->

| | Count |
|---|---|
| Pairs in | TBD |
| Removed: identity claims | TBD |
| Removed: duplicates | TBD |
| Removed: empty / too short / too long | TBD |
| Pairs out (train / val / test) | TBD |

## Verification

```bash
uv run pytest -v        # filters, dedupe, missing-column error, reproducibility
uv run ruff check .
uv lock --check
```

Running twice on the same input and `params.yaml` gives identical
`split_sha256` hashes in `report.json`.
