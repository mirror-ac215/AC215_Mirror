# Mirror persona-data cleaning (M2-09)

## Purpose

Turns the raw persona prompt/response pairs into a clean, versioned dataset for
the LoRA retrain (M3-09). The persona must never claim to be a doctor,
psychologist, professor or a real person, thus any response that makes an
identity or credential claim is removed, not rewritten. Every removal is
recorded with its reason.

Steps, in this order:

1. **Read** `data/raw/persona/jbp_clean_full.csv` (restored by DVC): columns
   `question` and `answer`. The old `jbp_train/val/test.csv` split files hold
   the same rows and are ignored. The `formatted` column (the old training
   prompt, which names the real person) is dropped; M3-09 builds Mirror's own
   prompt.
2. **Normalise** whitespace (wording and case are kept).
3. **Drop** empty pairs and answers shorter than 12 or longer than 1,000
   characters: see [How the length limits were chosen](#how-the-length-limits-were-chosen).
4. **Filter identity/credential claims** with the regex list in `params.yaml`
   (`identity_filters`), e.g. "I am Dr…", "as a clinical psychologist",
   "my patients", and the source person's name, employer, books and family.
   Each rule has an id, the report says which rule fired. Questions that
   address the persona by name ("Peterson, let's discuss…") are removed too
   (`prompt_filters`), since they would teach the model it is that person.
5. **Dedupe** exact duplicates (ignoring case and spacing).
6. **Split** 80/10/10 into train/val/test with seed 215.

## How the identity filter works

**Why:** Mirror is a support companion, not a clinician and not a real person.
The source answers are written in Jordan Peterson's voice, some of them say
things like "I am a psychology professor… a clinical psychologist". If the model
learned from those, it could tell a patient it is a doctor or a real person.

**The rule of thumb:** first person + credential = removed;
just mentioning a profession = kept. The persona may say "it might help to talk
to a psychologist"; it must never say "as a psychologist, I…".

**How it works:** `params.yaml` holds a list of named text patterns (regular
expressions). Each answer is checked against them in order. If one matches, the
whole pair is removed (never rewritten) and the rule's name is written to
`removed.csv` as the reason.

| Rule | Removes answers like | Keeps answers like |
|---|---|---|
| `doctor_title` | "I'm Dr. …", "I am a doctor" | "see a doctor" |
| `clinical_role` | "As a clinical psychologist…", "I'm a licensed therapist", "as a clinical practitioner" | "talk to a psychologist" |
| `professor_claim` | "I am a psychology professor…" | "my professor said…" |
| `my_patients` | "my patients", "my clients", "my practice" | "patients often feel…" |
| `clinical_experience` | "in my clinical practice / work" | "in my experience" |
| `my_works` | "my book", "my lectures", "my podcast", "my students" | "a good book on this" |
| `named_identity` | his name, "University of Toronto", his book titles, family names | — |

**Questions are checked too, for the name only** (`prompt_filters`). A question
like "Peterson, let's discuss…" teaches the model it *is* Peterson even when the
answer is harmless, the pair is removed. However, "Should I see a psychologist?" stays.

**On the real data** this removed 10 pairs: 6 answers with an identity claim and
4 questions that address the persona by name.

**Limits:** patterns only catch wording they describe. A claim phrased in an
unexpected way could slip through. As a second check, the kept data was searched
by hand for `psycholog|professor|clinic|patient|toronto|peterson|practitioner`
(only neutral uses remain), and M3-09 tests the retrained model on 30 probe
prompts for identity claims.

## How the length limits were chosen

Both limits are in **characters**, not words, and were set by looking at the
real data rather than guessing.

**Minimum: 12 characters (about 2 words).**
- The first draft used 20. On the real data that removed 33 answers (9%),
  including short but genuine replies. People often answer briefly, and that is
  part of a natural, human-sounding style.
- Lowering it to 12 removes only 12 throwaway replies that carry no persona or
  meaning: "Yes.", "Yeah." (×3), "Yup.", "No.", "Gotcha!", "HAHAHA",
  "Exactly.", "Honesty.", "Pointless.", "Or 'good.'"
- Every removed answer is listed in `removed.csv` (reason `too_short`), then the
  cut can be checked.

**Maximum: 1,000 characters (about 150 words, ~10 sentences).**
- This is a safety net for broken rows (e.g. a whole transcript pasted into one
  cell), not a style rule. On this data it removed nothing.
- Measured answer lengths: median **85** characters (~1 sentence), 90% under
  **185** (~2 sentences), longest **317** (~3–4 sentences). 1,000 is about 3×
  the longest real answer.
- The first draft used 4,000 (~1 page), which is far beyond any real answer and
  hard to justify.
- A cap of 200 was considered and rejected: it would delete the longest ~10% of
  answers, which are the most thoughtful, reflective ones, the style we want
  the persona to learn.

**How long Mirror's replies are is controlled elsewhere**, not by deleting
training data: by the prompt template (M3-08, e.g. "answer in 2–4 sentences")
and by a `max_tokens` limit in the LLM service.

**Note for M3-09:** the training answers are short (median about one sentence),
so the retrained model may reply briefly. Compare reply lengths in the M4-09
evaluation and adjust the prompt if it sounds curt.

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

First run, 12 Oct 2026 (`report.json`, seed 215):

| | Count |
|---|---|
| Pairs in (`jbp_clean_full.csv`) | 380 |
| Removed: too short (< 12 chars: "Yes.", "Yeah.", "Gotcha!"...) | 12 |
| Removed: identity claim in the answer | 6 (named identity 3, professor 1, clinical role 1, own works 1) |
| Removed: question addresses the persona by name | 4 |
| Removed: duplicates / empty / too long | 0 |
| **Pairs out** | **358** (train 286 / val 36 / test 36) |

Every removal is listed with its source row and rule in `removed.csv`.
After the run, a search of the kept data for `psycholog|professor|clinic|patient|toronto|peterson`
only finds neutral uses (e.g. "not a psychologist", "psychologically").

## Verification

```bash
uv run pytest -v        # filters, dedupe, missing-column error, reproducibility
uv run ruff check .
uv lock --check
```

Running twice on the same input and `params.yaml` gives identical
`split_sha256` hashes in `report.json`.
