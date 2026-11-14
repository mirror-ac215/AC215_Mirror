# Evaluation gates (M4-09)

Status: **experimental.** These harnesses are evaluation infrastructure only. No output from them
is reported as an accepted result until every gate below is met and recorded in this file.
They do not select a CV model, a dataset or a training protocol: those decisions stay with
Mostafa (CV and training owner).

Items marked **[TEAM TO AGREE]** are open decisions. Fill them in, with the date and who agreed,
before the first scored run.

## Gate 1: harmful-completion rubric

- The labelling rule is [`HARM_LABELLING.md`](HARM_LABELLING.md) (refuse / complete / unclear).
- Agreed by: **[TEAM TO AGREE: names, date]**.
- Any change to the rule after agreement restarts Gate 2.

## Gate 2: rater agreement (Cohen's kappa)

- Two raters label the same sample of 20 replies, independently, with the rule from Gate 1.
- Kappa is computed with `cohen_kappa` in `src/mirror_pairwise/harm.py`.
- Interpretation: Landis and Koch bands (0.41–0.60 moderate, 0.61–0.80 substantial,
  0.81–1.00 almost perfect).
- Pass threshold: **[TEAM TO AGREE: minimum kappa]**.
- Below the threshold: tighten the rule (`HARM_LABELLING.md`, rules 1–2), label a new sample of
  20 and compute kappa again. The full set is not scored until a sample passes.
- Recorded result: **[kappa, number of unclear labels, date]**.

## Gate 3: raters and blinding

- Raters: **[TEAM TO AGREE: who rates; a rater does not generate or select the replies they rate]**.
- Rater instructions: [`RATERS.md`](RATERS.md).
- Blinding: `pairwise.write_blinded` writes `comparisons.jsonl` (what raters see, in random A/B
  order) and `key.json` (which model is A or B). Comparison IDs are opaque (`c0001`, ...), with
  the prompt and the pair kept only in `key.json`; a test checks that no visible field names a model.
- Key holder: **[TEAM TO AGREE: one person, not a rater]**. The key is opened only after all
  ratings are in `ratings.jsonl`.
- Position bias: the tally reports the share of A picks; a share far from 50% is noted in the report.

## Gate 4: inputs, provenance and storage

| Input | Source | Where it lives |
|---|---|---|
| Held-out prompts | Persona test split, never seen in training (`split.held_out`, fixed seed) | DVC (`data/processed/persona/v1`) |
| Model replies | Generated on the GPU stack from base, LoRA and LoRA with visual context | GCS run folder, not Git |
| Ratings and labels | Raters, per Gate 3 | GCS run folder, not Git |
| IEMOCAP table (modality-eval) | `pipelines/iemocap-data` stage `iemocap_build`, licensed dataset | DVC (`data/processed/iemocap/v1`) |
| Face readings per utterance (modality-eval) | Second PR of M3-21: **not built yet** | Not available; modality-eval stays unscored until it exists |

Never committed to Git: raw frames, prompts with replies, `comparisons.jsonl`, `key.json`,
`ratings.jsonl`, harm labels, or model artifacts. Each harness has a `.gitignore` for its run
outputs, and the repository `.gitignore` already excludes `data/` and model weights.

## Sign-off

| Gate | Met on | By |
|---|---|---|
| 1 Rubric | | |
| 2 Kappa | | |
| 3 Raters and blinding | | |
| 4 Inputs | | |
