"""M2-11: compare two pretrained text-emotion classifiers.

Usage:
    uv run python compare.py data/m2-11_messages_to_label.csv

Reads Julie's hand-labelled messages, runs both models on CPU, and prints
accuracy, macro-F1 and latency per model. Writes per-message predictions
to results/predictions.csv so every number can be checked by hand.
"""

import sys
import time
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from transformers import pipeline

# Mirror's 7 text labels (same names as model A and the contract).
LABELS = ["anger", "disgust", "fear", "joy",
          "neutral", "sadness", "surprise"]

MODEL_A = "j-hartmann/emotion-english-distilroberta-base"
MODEL_B = "SamLowe/roberta-base-go_emotions"

# Model B outputs 28 GoEmotions labels. This is the official
# GoEmotions -> Ekman mapping published with the dataset.
GOEMOTIONS_TO_MIRROR = {
    "anger": ["anger", "annoyance", "disapproval"],
    "disgust": ["disgust"],
    "fear": ["fear", "nervousness"],
    "joy": ["joy", "amusement", "approval", "excitement",
            "gratitude", "love", "optimism", "relief", "pride",
            "admiration", "desire", "caring"],
    "sadness": ["sadness", "disappointment", "embarrassment",
                "grief", "remorse"],
    "surprise": ["surprise", "realization", "confusion", "curiosity"],
    "neutral": ["neutral"],
}


def clean(series):
    return (series.fillna("").astype(str).str.strip().str.lower()
            .replace({"happy": "joy"}))


def load_labels(path):
    df = pd.read_csv(path)
    df["label"] = clean(df["label"])
    df["second_label"] = clean(df["second_label"])
    bad = df[~df["label"].isin(LABELS)]
    if len(bad):
        sys.exit(f"Unknown or missing labels in rows: {bad['id'].tolist()}")
    return df


def scores_model_a(output):
    """Model A already uses Mirror's 7 labels."""
    return {o["label"]: o["score"] for o in output}


def scores_model_b(output):
    """Collapse 28 GoEmotions scores into 7 (strongest member wins)."""
    raw = {o["label"]: o["score"] for o in output}
    grouped = {m: max(raw.get(g, 0.0) for g in members)
               for m, members in GOEMOTIONS_TO_MIRROR.items()}
    total = sum(grouped.values()) or 1.0
    return {k: v / total for k, v in grouped.items()}


def run(model_name, to_scores, texts):
    clf = pipeline("text-classification", model=model_name,
                   top_k=None, device=-1)
    clf("warm-up message")  # first call is slow; don't count it
    all_scores, latencies = [], []
    for text in texts:
        start = time.perf_counter()
        output = clf(text, truncation=True)
        latencies.append((time.perf_counter() - start) * 1000)
        if output and isinstance(output[0], list):
            output = output[0]
        all_scores.append(to_scores(output))
    return all_scores, latencies


def report(name, df, scores, latencies):
    preds = [max(s, key=s.get) for s in scores]
    gold = df["label"].tolist()
    lenient = [p == g or p == s
               for p, g, s in zip(preds, gold, df["second_label"])]
    present = sorted(set(gold))
    lat = pd.Series(latencies)
    summary = {
        "model": name,
        "accuracy": accuracy_score(gold, preds),
        "accuracy_incl_second_label": sum(lenient) / len(gold),
        "macro_f1": f1_score(gold, preds, labels=present,
                             average="macro", zero_division=0),
        "median_ms": lat.median(),
        "p95_ms": lat.quantile(0.95),
    }
    print(f"\n=== {name} ===")
    for k, v in summary.items():
        if k == "model":
            continue
        if "ms" in k:
            print(f"{k:28s} {v:.1f}")
        else:
            print(f"{k:28s} {v:.3f}")
    print("confusion matrix (rows = your label, columns = model):")
    matrix = confusion_matrix(gold, preds, labels=present)
    print(pd.DataFrame(matrix, index=present, columns=present))
    return {"summary": summary, "preds": preds, "scores": scores}


def main():
    df = load_labels(sys.argv[1])
    texts = df["text"].tolist()
    models = [("A", MODEL_A, scores_model_a),
              ("B", MODEL_B, scores_model_b)]
    results = {}
    for key, model_name, to_scores in models:
        scores, latencies = run(model_name, to_scores, texts)
        results[key] = report(f"{key}: {model_name}",
                              df, scores, latencies)

    out = df[["id", "text", "label", "second_label"]].copy()
    for key, r in results.items():
        out[f"pred_{key}"] = r["preds"]
        out[f"top2_{key}"] = [
            [[k, round(v, 2)]
             for k, v in sorted(s.items(), key=lambda kv: -kv[1])[:2]]
            for s in r["scores"]]
    Path("results").mkdir(exist_ok=True)
    out.to_csv("results/predictions.csv", index=False)
    summaries = [r["summary"] for r in results.values()]
    pd.DataFrame(summaries).to_csv("results/summary.csv", index=False)
    print("\nWrote results/predictions.csv and results/summary.csv")


if __name__ == "__main__":
    main()