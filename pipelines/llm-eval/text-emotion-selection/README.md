# M2-11: Text-emotion classifier selection

One-off experiment (not a container) that picks the text-emotion model for
the api-gateway (M3-05). Decision and full results: `docs/decisions.md`, D-003.

## Candidates
- A: `j-hartmann/emotion-english-distilroberta-base` (7 labels) — **chosen**
- B: `SamLowe/roberta-base-go_emotions` (28 labels, mapped to 7)

## Data
EmpatheticDialogues (Rashkin et al., ACL 2019), official test split.
Download it to a folder **outside the repo** (raw data never goes in git):

    mkdir -p ~/datasets && cd ~/datasets
    curl -LO https://dl.fbaipublicfiles.com/parlai/empatheticdialogues/empatheticdialogues.tar.gz
    tar -xzf empatheticdialogues.tar.gz      # -> ~/datasets/empatheticdialogues/test.csv

`test.csv` SHA-256: `a014199d689a11bfd58c19a406ccf18c4fdffd1eb45c5eb31a3a1c880dc15958`

## Run

    uv sync
    uv run python sample_empathetic.py ~/datasets/empatheticdialogues/test.csv   # draws the 50 (seed 215)
    uv run python compare.py data/m2-11_messages_to_label.csv                    # 50 hand-labelled
    uv run python compare_full.py ~/datasets/empatheticdialogues/test.csv        # full test split

`compare_full.py` skips messages that mention suicide or self-harm (and
dated pandemic/election content): in Mirror those messages go to the
deterministic crisis check (M3-07) before any emotion model runs, so the
classifier is never the safety path.

`data/` is gitignored (team rule). Julie's 50 labels are preserved in
`results/predictions.csv` (columns `label`, `second_label`).

## Results

**Evaluation 1: full test split** (n = 2,543, scored against the authors' emotion tags)

| Model | Accuracy | Macro-F1 | Says neutral | ms / message |
|---|---|---|---|---|
| A (chosen) | 0.571 | 0.556 | 8.8% | 4.5 |
| B | 0.534 | 0.526 | 23.5% | 8.8 |

**Evaluation 2: 50 hand-labelled messages** (scored against Julie's labels)

| Model | Accuracy | Incl. 2nd label | Macro-F1 | Median / p95 ms |
|---|---|---|---|---|
| A (chosen) | 0.48 | 0.50 | 0.455 | 8.1 / 11.4 |
| B | 0.48 | 0.48 | 0.407 | 15.2 / 20.5 |

Recall per label, the limits of each evaluation and the reasoning are in D-003.

### What the results show

- **A wins on the large evaluation:** higher accuracy and macro-F1, and
  better recall on 4 of 6 labels (anger, disgust, fear, surprise).
- **A is about twice as fast** (4.5 vs 8.8 ms per message), well under
  the gateway's 100 ms budget.
- **B leans on neutral:** it says neutral for 23.5% of messages that all
  carry a real emotion tag, which would hide distress from the clinician
  dashboard.
- **B is better on joy and sadness** (0.70 and 0.53 recall vs A's 0.61 and 0.48),
  and A's sadness recall is its weakest point.
- **The 50-message test is a tie on accuracy** (0.48 each) and too small to
  decide on alone, but A still leads on macro-F1 (0.455 vs 0.407).

## Files
| File | Purpose |
|---|---|
| `sample_empathetic.py` | Draws the 50 messages with a fixed seed |
| `compare.py` | Scores both models on the hand-labelled 50 |
| `compare_full.py` | Scores both models on the full test split vs. author tags |
| `results/` | Summaries and per-message predictions (`full_split_predictions.csv` holds `conv_id` only, no dataset text; look messages up in `test.csv`) |
