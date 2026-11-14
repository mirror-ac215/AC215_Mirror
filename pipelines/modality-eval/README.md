# modality-eval (M4-09)

> **Experimental.** Evaluation infrastructure only: no result is reported as accepted until the
> gates in [`../llm-eval/pairwise/EVALUATION_GATES.md`](../llm-eval/pairwise/EVALUATION_GATES.md)
> are met. It compares signals; it does not select a CV model, dataset or training protocol
> (Mostafa's decisions). Raw frames and per-utterance outputs stay out of Git.

Compares what the face reading, the text reading and both together each add, on the
IEMOCAP evaluation table (`pipelines/iemocap-data`).

## Rules
- Scored labels: neutral, joy, anger, sadness. Fear (40) and disgust (2) are too rare
  and are not scored. Frustration has no Mirror label and is reported on its own.
- Text counts when its top probability is at least 0.40 (same bar as the prompt).
- Face counts only when the gate said "ok" (same rule as `fusion.py`).
- "both" is a plain rule: text when it counts, otherwise face. It is not the gateway's
  fusion, which leans towards negative signals; the difference is stated in the report.
- Each mode is scored on the rows where it gives a reading, and those subsets differ.
  The report also scores face and text on the overlap: only the rows where both give a reading.
- Intervals are Wilson 95%. A gap is "beyond noise" only when the intervals do not overlap.

## Input
One row per utterance: `label`, `text_label`, `text_prob`, `face_label`, `face_status`.
The face columns need the face frames per utterance (second PR of M3-21), which are not built yet.

## Tests
    uv sync && uv run pytest && uv run ruff check src tests
