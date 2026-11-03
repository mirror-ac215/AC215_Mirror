# IEMOCAP evaluation table (M3-21)

## Purpose

Builds the evaluation set for the M4-09 modality comparison (face only vs text
only vs both vs none), requested in the MS1 feedback. IEMOCAP (Busso et al.,
2008, USC SAIL) holds acted two-person conversations recorded on video and audio,
with transcripts and an emotion label for every utterance; one dataset therefore
tests both of Mirror's signals on the same moments.

This stage produces the **text side**: one row per utterance with its transcript,
IEMOCAP consensus label and Mirror label. Face frames per utterance follow in a
second PR; the videos are in `Session*/dialog/avi/`, and an unpacked copy of the
release is already in the bucket.

## Steps

1. **Read** only the label files (`Session*/dialog/EmoEvaluation/*.txt`) and
   transcripts (`Session*/dialog/transcriptions/*.txt`), streamed directly from
   the release archive in one pass. The 17.7 GB archive is never unpacked, and
   the videos are not read.
2. **Parse** the consensus label of each utterance (one line per utterance;
   per-annotator lines are ignored) and its transcript.
3. **Join** labels and transcripts by utterance id, e.g. `Ses01F_impro01_F000`
   = session 1, improvised dialogue 1, female speaker, first turn.
4. **Map** IEMOCAP labels to Mirror's 7 emotions (table below). Frustration is
   kept without a Mirror label; `oth`, `xxx` and utterances without a transcript
   are dropped. Both are counted in `report.json`.

## Label mapping

Mirror's 7 emotions are the classes of the camera model; matching them lets
M4-09 compare face and text one to one. Set in `params.yaml` (`labels`).

The `label` column uses the **text model's names** (`anger`, `joy`, `sadness`),
while the camera model returns `angry`, `happy`, `sad` for the same three
emotions; the other four names are identical. M4-09 compares the two with the
gateway's existing mapping, `TEXT_TO_FACE` in
`services/api-gateway/app/fusion.py` (line 28): `anger -> angry`,
`joy -> happy`, `sadness -> sad`. No second mapping is introduced here.

| IEMOCAP code | Meaning | Mirror |
|---|---|---|
| `neu` | neutral | neutral |
| `hap` | happiness | joy |
| `exc` | excited | joy (merged with happiness, as is common in IEMOCAP studies) |
| `sad` | sadness | sadness |
| `ang` | anger | anger |
| `fea` | fear | fear |
| `dis` | disgust | disgust |
| `sur` | surprise | surprise |
| `fru` | frustration | **kept, no Mirror label** (see below) |
| `oth`, `xxx` | other / no annotator agreement | **dropped** |

**Why frustration is kept without a label.** Mirror's 7 emotions have no match for
frustration: it is not anger (lower intensity, aimed at a situation rather than a
person), and it shows mostly in voice and words, while a frustrated face often
reads as neutral or sad. Mapping it to anger would mark both models wrong when they
are arguably right; dropping it would lose one of IEMOCAP's largest labels and an
emotion patients often feel. Frustration rows therefore stay in the table with an
empty `label` (`keep_unlabelled` in `params.yaml`): they are left out of the face
vs text scores, and M4-09 reports separately what each signal reads for them. To
drop them, set `keep_unlabelled: []`; to map them to anger, add `fru: anger` under
`labels`. Tests cover all three settings and all 11 IEMOCAP codes.

## Inputs and outputs

| | Path | In git? |
|---|---|---|
| Input | `data/raw/iemocap/IEMOCAP_full_release.tar.gz` | No, DVC (private bucket) |
| Output | `data/processed/iemocap/v1/utterances.csv`: `utterance_id, session, dialog, speaker, kind, start_s, end_s, iemocap_label, label, valence, arousal, dominance, text` | No, DVC |
| Output | `data/processed/iemocap/v1/report.json`: label counts before and after, frustration rows kept, drops by reason, per-session counts, table hash | No, DVC |

## Licence and storage

IEMOCAP is released by USC SAIL under a signed release form: **academic,
non-commercial use only; no redistribution**. Consequently:

- the archive and every output stay in the team's private bucket
  (`gs://mirror-ac215-data`), accessed through DVC; nothing is committed to git;
- the tests use a small invented release with the same layout, never real data;
- access was requested with a Harvard account (Julie, received Oct 19, 2026);
- the release form covers the project team: every Mirror member may read the
  archive and the outputs in `gs://mirror-ac215-data`; nobody outside the team.

## Run (fresh clone)

The archive is in the bucket at
`gs://mirror-ac215-data/data/raw/iemocap/IEMOCAP_full_release.tar.gz`
(17,695,884,032 bytes). It is tracked with `dvc import-url --no-download` (`raw-iemocap.dvc` at the
repo root, like `raw-fer2013.dvc`); `dvc pull` fetches it. Credentials: a Google account with access to the
`mirror-ac215` project.

```bash
gcloud auth application-default login                        # choose the project account
dvc repro iemocap_build
dvc push                                                     # share the new output
```

Without DVC (same result; an extracted release folder also works as `--input`):

```bash
cd pipelines/iemocap-data
uv sync
uv run mirror-iemocap-data --params params.yaml \
  --input ../../data/raw/iemocap/IEMOCAP_full_release.tar.gz \
  --output ../../data/processed/iemocap/v1
```

With Docker (data mounted, never baked into the image):

```bash
docker build -t mirror-iemocap-data pipelines/iemocap-data
docker run --rm -v "$PWD/data:/app/data" mirror-iemocap-data
```

**Env vars / secrets:** none for the job itself. `dvc pull` and `dvc push` need
Google Application Default Credentials (see `secrets/README.md`).

## Verification

```bash
uv run pytest -v     # parsing, all 11 label codes, drops, archive = folder, reproducibility
uv run ruff check .
uv lock --check
```

Running twice on the same input and `params.yaml` gives an identical
`utterances_sha256` in `report.json`.

## Results

First run on the full release (Nov 3, 2026), from `report.json`.
`utterances_sha256`: `cdfe975e75d63e37c2c4c52f67af3d3c6505b22c15b8b0d87503115770d2bce5`.

**Read:** 151 label files and 151 transcript files (5 sessions), 10,039
labelled utterances.

**Dropped (2,510):** 2,507 `xxx` (annotators did not agree) and 3 `oth`. No
utterance was dropped for a missing transcript.

**Kept (7,529):** 5,680 with a Mirror label and 1,849 frustration rows kept
without one.

| Mirror label | IEMOCAP codes | Utterances | Share of the 5,680 |
|---|---|---|---|
| neutral | `neu` | 1,708 | 30.1% |
| joy | `hap` 595 + `exc` 1,041 | 1,636 | 28.8% |
| anger | `ang` | 1,103 | 19.4% |
| sadness | `sad` | 1,084 | 19.1% |
| surprise | `sur` | 107 | 1.9% |
| fear | `fea` | 40 | 0.7% |
| disgust | `dis` | 2 | <0.1% |
| *(none: frustration)* | `fru` | 1,849 | kept, not scored |

**Per session (kept rows):** 1: 1,403 · 2: 1,374 · 3: 1,564 · 4: 1,538 · 5: 1,650.

**For M4-09.** Four labels (neutral, joy, anger, sadness) hold 97% of the
scored rows. Fear (40) and disgust (2) are too rare for a reliable
per-label score. M4-09 should therefore report its main face vs text
comparison on those four labels, and list surprise, fear and disgust
separately with their counts. Frustration (1,849 rows) is reported on its
own, as described above.
