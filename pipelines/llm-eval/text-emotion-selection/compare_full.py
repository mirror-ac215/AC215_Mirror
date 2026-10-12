"""M2-11 part 2: score both models on the full EmpatheticDialogues test split.

Usage:
    uv run python compare_full.py ~/datasets/empatheticdialogues/test.csv

Gold labels are each conversation's own emotion tag (written by its
author), grouped into Mirror's labels. The dataset has no neutral tag,
so a 'neutral' prediction always counts as wrong; we report how often
each model says neutral separately.
"""

import collections
import re
import sys
import time

import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, recall_score
from transformers import pipeline

from compare import MODEL_A, MODEL_B, scores_model_a, scores_model_b

GROUPS = {
    "anger": ["angry", "annoyed", "furious", "jealous"],
    "disgust": ["disgusted"],
    "fear": ["afraid", "anxious", "apprehensive", "terrified"],
    "joy": ["joyful", "excited", "content", "grateful", "hopeful",
            "proud", "confident", "caring", "trusting", "faithful",
            "prepared", "anticipating"],
    "sadness": ["sad", "devastated", "lonely", "disappointed",
                "guilty", "ashamed", "embarrassed", "nostalgic",
                "sentimental"],
    "surprise": ["surprised", "impressed"],
}
TO_GROUP = {e: g for g, es in GROUPS.items() for e in es}
SKIP = re.compile(
    r"suicid|kill myself|self.?harm|end my life|cutting"
    r"|covid|corona|pandemic|lockdown|quarantin|vaccin|election",
    re.I,
)


def load(path):
    convs = {}
    with open(path, encoding="utf-8") as f:
        next(f)
        for line in f:
            p = line.rstrip("\n").split(",")
            if len(p) < 4 or p[0] in convs:
                continue
            text = " ".join(p[3].replace("_comma_", ",").split())
            convs[p[0]] = (p[2], text)
    print("conversations in file:", len(convs))
    print("distinct emotion tags:", len({e for e, _ in convs.values()}))
    rows = [(cid, TO_GROUP[e], t) for cid, (e, t) in convs.items()
            if e in TO_GROUP and not SKIP.search(t)]
    df = pd.DataFrame(rows, columns=["conv_id", "gold", "text"])
    print("used after filters:", len(df))
    print("gold labels:", df["gold"].value_counts().to_dict())
    return df


def run(model_name, to_scores, texts):
    clf = pipeline("text-classification", model=model_name,
                   top_k=None, device=-1)
    start = time.perf_counter()
    outputs = clf(texts, truncation=True, batch_size=32)
    seconds = time.perf_counter() - start
    preds = []
    for o in outputs:
        scores = to_scores(o)
        preds.append(max(scores, key=scores.get))
    return preds, seconds


def main():
    df = load(sys.argv[1])
    labels = sorted(GROUPS)
    rows = []
    for key, name, fn in [("A", MODEL_A, scores_model_a),
                          ("B", MODEL_B, scores_model_b)]:
        preds, seconds = run(name, fn, df["text"].tolist())
        df[f"pred_{key}"] = preds
        recalls = recall_score(df["gold"], preds, labels=labels,
                               average=None, zero_division=0)
        row = {
            "model": key,
            "n": len(df),
            "accuracy": accuracy_score(df["gold"], preds),
            "macro_f1": f1_score(df["gold"], preds, labels=labels,
                                 average="macro", zero_division=0),
            "said_neutral": collections.Counter(preds)["neutral"] / len(df),
            "ms_per_msg": 1000 * seconds / len(df),
        }
        row.update({f"recall_{l}": r for l, r in zip(labels, recalls)})
        rows.append(row)
    summary = pd.DataFrame(rows).set_index("model").T
    print("\n", summary.round(3).to_string())
    summary.to_csv("results/full_split_summary.csv")
    # No dataset text in git (team rule): conv_id is enough to look a message up.
    df.drop(columns=["text"]).to_csv("results/full_split_predictions.csv", index=False)
    print("\nWrote results/full_split_summary.csv")


if __name__ == "__main__":
    main()