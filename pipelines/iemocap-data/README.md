# IEMOCAP evaluation table (M3-21)

## Purpose

Builds the evaluation set for the M4-09 modality comparison (face only vs text
only vs both vs none), requested in the MS1 feedback. IEMOCAP (Busso et al.,
2008, USC SAIL) holds acted two-person conversations recorded on video and audio,
with transcripts and an emotion label for every utterance; one dataset therefore
tests both of Mirror's signals on the same moments.

This stage produces the **text side**: one row per utterance with its transcript,
IEMOCAP consensus label and Mirror label. Face frames per utterance follow in a
second PR, once the video layout of the release is confirmed.

## Steps

1. **Read** only the label files (`Session*/dialog/EmoEvaluation/*.txt`) and
   transcripts (`Session*/dialog/transcriptions/*.txt`), streamed directly from
   the release archive in one pass. The 17.7 GB archive is never unpacked, and
   the videos are not read.
2. **Parse** the consensus label of each utterance (one line per utterance;
   per-annotator lines are ignored) and its transcript.
3. **Join** labels and transcripts by utterance id, e.g. `Ses01F_impro01_F000`
   = session 1, improvised dialogue 1, female speaker, first turn.
4. **Map** IEMOCAP labels to Mirror's 7 emotions (table below); unmapped labels
   and utterances without a transcript are dropped and counted.

## Label mapping

Mirror's 7 emotions are the classes of the camera model; matching them lets
M4-09 compare face and text one to one. Set in `params.yaml` (`labels`).

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
| `fru` | frustration | **dropped**: no clean match; frustration is not anger |
| `oth`, `xxx` | other / no annotator agreement | **dropped** |

To map frustration to anger instead, add `fru: anger` under `labels`; a test
covers this case.

## Inputs and outputs

| | Path | In git? |
|---|---|---|
| Input | `data/raw/iemocap/IEMOCAP_full_release.tar.gz` | No, DVC (private bucket) |
| Output | `data/processed/iemocap/v1/utterances.csv`: `utterance_id, session, dialog, speaker, kind, start_s, end_s, iemocap_label, label, valence, arousal, dominance, text` | No, DVC |
| Output | `data/processed/iemocap/v1/report.json`: label counts before and after, drops by reason, per-session counts, table hash | No, DVC |

## Licence and storage

IEMOCAP is released by USC SAIL under a signed release form: **academic,
non-commercial use only; no redistribution**. Consequently:

- the archive and every output stay in the team's private bucket
  (`gs://mirror-ac215-data`), accessed through DVC; nothing is committed to git;
- the tests use a small invented release with the same layout, never real data;
- access was requested with a Harvard account (Julie, received Oct 19, 2026).

## Run (fresh clone)

From the repository root, with Google Application Default Credentials for the
`mirror-ac215` project:

```bash
gcloud auth application-default login
dvc pull data/raw/iemocap/IEMOCAP_full_release.tar.gz.dvc   # the archive (17.7 GB)
dvc repro iemocap_build                                      # this stage
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
uv run pytest -v     # parsing, label mapping, drops, archive = folder, reproducibility
uv run ruff check .
uv lock --check
```

Running twice on the same input and `params.yaml` gives an identical
`utterances_sha256` in `report.json`.

## Results

To be filled after the first run on the real release: utterances kept per
label, drops by reason, per-session counts.
