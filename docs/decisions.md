# Mirror decision log

This log records cross-component decisions that affect more than one owner or
that must be preserved when an implementation pull request is later merged.
It does not turn an unmerged pull request into merged functionality.

## Status values

- **Accepted** — the team has agreed the decision and implementation can rely on it.
- **Proposed** — awaiting the affected owners' review; do not treat it as a
  merged implementation fact.
- **Superseded** — kept for history, but replaced by a later decision.

## D-001: Keep local DVC reproduction separate from shared GCS publication

- **Status:** Accepted for M2-06; implementation is pending merge.
- **Decision:** `dvc repro` validates and materializes the declared local
  processed-data output only. Uploading to the versioned GCS artifact prefix is
  a separate explicit `--publish` action.
- **Why:** A normal reproducibility check should not require cloud credentials
  or silently change shared storage. Explicit publication makes shared state
  intentional and auditable.
- **Affected areas:** `dvc.yaml`, preprocessing README, artifact inventory,
  and future training/evaluation consumers.

## D-002: Use Node/Nitro SSR for the frontend runtime

- **Status:** Proposed pending M2-12 Part A review and merge.
- **Decision:** The frontend target is a Node/Nitro server-side-rendering
  runtime on port 3000, with an unauthenticated `GET /health` endpoint, rather
  than an nginx-only static runtime.
- **Why:** TanStack Start requires a server runtime for SSR and its route-based
  health endpoint. Caddy/Compose integration must route to this documented
  runtime after M2-03 is implemented.
- **Affected areas:** frontend Dockerfile/README, architecture, Compose, Caddy,
  and deployment documentation.

## D-003: Use j-hartmann/emotion-english-distilroberta-base for text emotion

- **Status:** Proposed for M2-11, pending review (Samuel).
- **Decision:** The api-gateway text-emotion module (M3-05) uses
  `j-hartmann/emotion-english-distilroberta-base`. It outputs Mirror's 7
  labels directly: anger, disgust, fear, joy, neutral, sadness, surprise.
  These are the 7 emotions of the project's camera model (FER-2013), so
  face and text can be compared in the context object.
- **Candidates compared:**
  - A: `j-hartmann/emotion-english-distilroberta-base` (DistilRoBERTa,
    7 labels; Jochen Hartmann, University of Hamburg / TU Munich)
  - B: `SamLowe/roberta-base-go_emotions` (RoBERTa trained on Google
    Research's GoEmotions, 28 labels, mapped to the 7 with the official
    GoEmotions-to-Ekman mapping)
  - Both are BERT-family encoders with a classification head on the [CLS]
    token, used as pretrained checkpoints (transfer learning, AC215 L07).
- **Evaluation data:** EmpatheticDialogues (Rashkin, Smith, Li & Boureau,
  ACL 2019; University of Washington and Facebook AI Research), a
  peer-reviewed benchmark of 24,850 conversations written by 810 US
  participants. Each conversation is grounded in a real personal situation
  the participant described in their own words (1–3 sentences, 19.8 words
  on average) and is tagged by its author with one of 32 fine-grained
  emotions. Neither candidate model was trained on this dataset. We used
  only the official held-out test split (2,547 conversations), which is
  never used for training.
  - Source paper: https://aclanthology.org/P19-1534.pdf (Section 3)
  - Dataset `test.csv` SHA-256: `a014199d689a11bfd58c19a406ccf18c4fdffd1eb45c5eb31a3a1c880dc15958`
- **Evaluation 1, full test split (author-tagged):** 2,543 conversations
  after excluding self-harm and dated pandemic/election content. Gold label
  is each author's own emotion tag, with all 32 tags grouped into Mirror's
  labels (joy 941, sadness 694, anger 322, fear 293, surprise 207,
  disgust 86). The dataset has no neutral tag, so a neutral prediction
  counts as wrong.

  | | Accuracy | Macro-F1 | Says neutral | ms/msg |
  |---|---|---|---|---|
  | A | **0.571** | **0.556** | 8.8% | 4.5 |
  | B | 0.534 | 0.526 | 23.5% | 8.8 |

  | Recall | anger | disgust | fear | joy | sadness | surprise |
  |---|---|---|---|---|---|---|
  | A | **0.44** | **0.80** | **0.73** | 0.61 | 0.48 | **0.56** |
  | B | 0.26 | 0.33 | 0.55 | **0.70** | **0.53** | 0.30 |

- **Evaluation 2, hand-labelled sample:** 50 situations drawn from the test
  split by a reproducible stratified sample (seed 215). Julie labelled each
  one blind, before seeing any model output, into Mirror's 7 labels
  including neutral (fear 10, joy 9, neutral 9, anger 7, surprise 5,
  sadness 5, disgust 5).
  - Labels SHA-256: `91d5f6c04e036d09d930ec597410af98124ac4e00e8f1a1df29cf4fdf23bf472`

  | | Accuracy | Acc. incl. 2nd label | Macro-F1 | Median ms | p95 ms |
  |---|---|---|---|---|---|
  | A | 0.48 | 0.50 | **0.455** | 8.1 | 11.4 |
  | B | 0.48 | 0.48 | 0.407 | 15.2 | 20.5 |

- **Why A:**
  - Wins on both evaluations by macro-F1, and on accuracy where the sample
    is large enough to tell (2,543 messages, about ±2 points).
  - Much better on the emotions that drive Mirror's tone and safety:
    fear (0.73 vs 0.55), anger (0.44 vs 0.26), disgust (0.80 vs 0.33).
  - B labels nearly a quarter of clearly emotional messages as neutral,
    which would hide distress from the fusion step.
  - Labels match the contract and pair one-to-one with the CV model's
    FER-2013 classes (happy↔joy, sad↔sadness, angry↔anger), so fusion
    needs no extra mapping step.
  - About twice as fast and smaller; well under M3-05's 100 ms budget.
- **Limits:**
  - The 50-message sample is small (accuracy tied, ±13 points), and has a
    single labeller with no agreement check.
  - EmpatheticDialogues has no neutral tag, so neutral is only tested on
    the 50, where A caught 1 of 9: it can read emotion into plain
    statements. The persona must never state emotion as fact and should
    ask when unsure; fusion should treat low-confidence text scores as
    uncertain.
  - Grouping 32 fine-grained tags into Mirror's labels involves judgement
    calls (e.g. nostalgic→sadness, prepared→joy), which makes full-split
    scores slightly pessimistic for both models equally.
  - Both models confuse fear with sadness, and A's sadness recall (0.48)
    is its weakest label. This is softened by design: the gateway passes
    the top-2 text emotions with their probabilities (`text.top2` in the
    context object), not a single label, so a missed sadness can still
    appear as the second label, and the persona treats emotion as
    uncertain rather than fact.
  - EmpatheticDialogues is everyday situations told to a stranger, not
    patients talking to a support companion.
- **Next:** package A as the gateway text-emotion module (M3-05) with unit
  tests and a <100 ms check; revisit with in-domain fine-tuning (AC215 L07)
  if neutral or sadness performance is a problem in M4 evaluation.
- **Affected areas:** `services/api-gateway` text_emotion module (M3-05),
  fusion and agreement flag (M3-06), context object `text.top2` labels.
- **Evidence:** `pipelines/llm-eval/text-emotion-selection/`
  (`compare.py`, `compare_full.py`, `results/`).
