"""Clean -> filter identity claims -> dedupe -> split the persona pairs.

Every removed pair is written to removed.csv with the reason, and
report.json holds before/after counts, so the cleaning can be explained
and audited. Same inputs + same params.yaml => byte-identical outputs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIELDS = ["pair_id", "prompt", "response"]


@dataclass(frozen=True)
class Pair:
    source: str  # file name + row number, so a removal can be traced back
    prompt: str
    response: str


def normalise(text: str) -> str:
    """Collapse whitespace and strip; keep wording and case unchanged."""
    return " ".join(str(text).split())


def read_pairs(raw_dir: Path, glob: str, prompt_col: str, response_col: str) -> list[Pair]:
    files = sorted(raw_dir.glob(glob))
    if not files:
        raise FileNotFoundError(f"no files matching {glob} in {raw_dir} (did you run dvc pull?)")
    pairs: list[Pair] = []
    for path in files:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = {prompt_col, response_col} - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"{path.name} is missing columns {sorted(missing)}; "
                                 f"found {reader.fieldnames}. Fix input.*_column in params.yaml")
            for i, row in enumerate(reader, start=2):  # row 1 is the header
                prompt, response = row[prompt_col] or "", row[response_col] or ""
                pairs.append(Pair(f"{path.name}:{i}", prompt, response))
    return pairs


def first_identity_hit(text: str, filters: dict[str, re.Pattern[str]]) -> str | None:
    for rule_id, pattern in filters.items():
        if pattern.search(text):
            return rule_id
    return None


def dedupe_key(pair: Pair) -> str:
    return hashlib.sha256(f"{pair.prompt.lower()}\x1f{pair.response.lower()}".encode()).hexdigest()


def clean(pairs: list[Pair], params: dict[str, Any]) -> tuple[list[Pair], list[dict[str, str]]]:
    """Return (kept pairs, removed rows with a reason). Order of checks is fixed."""
    min_chars = int(params["clean"]["min_response_chars"])
    max_chars = int(params["clean"]["max_response_chars"])
    filters = {k: re.compile(v, re.IGNORECASE) for k, v in params["identity_filters"].items()}
    prompt_filters = {k: filters[k] for k in params.get("prompt_filters", [])}
    kept: list[Pair] = []
    removed: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in pairs:
        pair = Pair(raw.source, normalise(raw.prompt), normalise(raw.response))
        reason = None
        if not pair.prompt or not pair.response:
            reason = "empty"
        elif len(pair.response) < min_chars:
            reason = "too_short"
        elif len(pair.response) > max_chars:
            reason = "too_long"
        elif rule := first_identity_hit(pair.response, filters):
            reason = f"identity:{rule}"
        elif rule := first_identity_hit(pair.prompt, prompt_filters):
            reason = f"identity_in_question:{rule}"
        elif (key := dedupe_key(pair)) in seen:
            reason = "duplicate"
        if reason:
            removed.append({"source": pair.source, "reason": reason,
                            "response_start": pair.response[:80]})
            continue
        seen.add(key)
        kept.append(pair)
    return kept, removed


def split(pairs: list[Pair], params: dict[str, Any]) -> dict[str, list[Pair]]:
    """Shuffle with a fixed seed, then cut into train/val/test."""
    order = sorted(pairs, key=dedupe_key)  # stable start order, independent of file order
    random.Random(int(params["split"]["seed"])).shuffle(order)
    n_train = round(len(order) * float(params["split"]["train"]))
    n_val = round(len(order) * float(params["split"]["val"]))
    return {"train": order[:n_train], "val": order[n_train:n_train + n_val],
            "test": order[n_train + n_val:]}


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(raw_dir: Path, out_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
    cfg = params["input"]
    pairs = read_pairs(raw_dir, cfg["glob"], cfg["prompt_column"], cfg["response_column"])
    kept, removed = clean(pairs, params)
    splits = split(kept, params)

    out_dir.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, rows in splits.items():
        path = out_dir / f"{name}.csv"
        _write_csv(path, FIELDS, [{"pair_id": dedupe_key(p)[:12], "prompt": p.prompt,
                                   "response": p.response} for p in rows])
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    _write_csv(out_dir / "removed.csv", ["source", "reason", "response_start"], removed)

    reasons = Counter(r["reason"] for r in removed)
    report = {
        "pairs_in": len(pairs),
        "pairs_out": len(kept),
        "removed_total": len(removed),
        "removed_by_reason": dict(sorted(reasons.items())),
        "split_counts": {k: len(v) for k, v in splits.items()},
        "split_sha256": hashes,
        "seed": int(params["split"]["seed"]),
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
