"""From per-photo predictions to per-group numbers and the largest gaps.

For every group (e.g. race = Black, gender = Female, age = 60-69):
- face_found:        share of photos where the Haar detector finds a face (cv-service step 1)
- gate_ok:           share where the full pipeline gives a trusted reading: face found AND
                     the gate passes (what the gateway would actually use)
- gate_ok_if_face:   the same, among photos with a face (the model alone, without the detector)
- confidence:        mean top probability
- share_<emotion>:   share of photos whose top emotion is <emotion>
- share_negative:    angry + disgust + fear + sad, the readings that matter most clinically

FairFace has no expression labels: these are differences in behaviour, not accuracy.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mirror_fairness_audit import LABELS
from mirror_fairness_audit.fairface import VALUES

NEGATIVE = ("angry", "disgust", "fear", "sad")
Z = 1.96  # 95% intervals


@dataclass(frozen=True)
class Row:
    race: str
    gender: str
    age: str
    face_found: bool
    probs: dict[str, float]

    @property
    def top(self) -> str:
        return max(self.probs, key=lambda label: self.probs[label])

    def ranked(self) -> tuple[float, float]:
        first, second = sorted(self.probs.values(), reverse=True)[:2]
        return first, second


def read_predictions(path: Path) -> list[Row]:
    with path.open(newline="") as handle:
        return [
            Row(
                race=r["race"],
                gender=r["gender"],
                age=r["age"],
                face_found=r["face_found"] == "True",
                probs={label: float(r[label]) for label in LABELS},
            )
            for r in csv.DictReader(handle)
        ]


def photo_gate(row: Row, min_top_prob: float, min_margin: float) -> bool:
    """The gateway's gate for one still photo: one steady frame, thus stability = 1.0."""
    top, second = row.ranked()
    return top >= min_top_prob and top - second >= min_margin


def wilson(successes: int, n: int) -> tuple[float, float]:
    """95% interval for a share; stays inside [0, 1] even for small groups."""
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    centre = (p + Z * Z / (2 * n)) / (1 + Z * Z / n)
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def _share(flags: Sequence[bool]) -> dict[str, float]:
    low, high = wilson(sum(flags), len(flags))
    return {"value": sum(flags) / len(flags) if flags else 0.0, "low": low, "high": high}


def _mean(values: Sequence[float]) -> dict[str, float]:
    n = len(values)
    mean = sum(values) / n if n else 0.0
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else 0.0
    half = Z * sd / math.sqrt(n) if n else 0.0
    return {"value": mean, "low": mean - half, "high": mean + half}


def group_metrics(rows: Sequence[Row], gate: dict[str, float]) -> dict[str, Any]:
    passed = [photo_gate(r, gate["min_top_prob"], gate["min_margin"]) for r in rows]
    with_face = [p for r, p in zip(rows, passed, strict=True) if r.face_found]
    metrics = {
        "face_found": _share([r.face_found for r in rows]),
        "gate_ok": _share([r.face_found and p for r, p in zip(rows, passed, strict=True)]),
        "gate_ok_if_face": _share(with_face),
        "confidence": _mean([r.ranked()[0] for r in rows]),
        "share_negative": _share([r.top in NEGATIVE for r in rows]),
    }
    for label in LABELS:
        metrics[f"share_{label}"] = _share([r.top == label for r in rows])
    return {"n": len(rows), "metrics": metrics}


def by_group(rows: Sequence[Row], attribute: str, gate: dict[str, float]) -> dict[str, Any]:
    """Every group of one attribute, in FairFace's order; empty groups are skipped."""
    out = {}
    for value in VALUES[attribute]:
        members = [r for r in rows if getattr(r, attribute) == value]
        if members:
            out[value] = group_metrics(members, gate)
    return out


def gaps(groups: dict[str, Any], min_size: int) -> list[dict[str, Any]]:
    """Per metric: highest minus lowest group, among groups with at least min_size photos.

    `separated` says whether the two 95% intervals do not overlap: a gap that is
    larger than the noise of the two groups.
    """
    sized = {g: v for g, v in groups.items() if v["n"] >= min_size}
    if len(sized) < 2:
        return []
    out = []
    for metric in next(iter(sized.values()))["metrics"]:
        values = {g: v["metrics"][metric] for g, v in sized.items()}
        high = max(values, key=lambda g: values[g]["value"])
        low = min(values, key=lambda g: values[g]["value"])
        out.append(
            {
                "metric": metric,
                "high_group": high,
                "high": values[high]["value"],
                "low_group": low,
                "low": values[low]["value"],
                "gap": values[high]["value"] - values[low]["value"],
                "separated": values[low]["high"] < values[high]["low"],
            }
        )
    return sorted(out, key=lambda item: item["gap"], reverse=True)


def audit(rows: Iterable[Row], params: dict[str, Any]) -> dict[str, Any]:
    rows = list(rows)
    groups_cfg, gate = params["groups"], params["gate"]
    excluded = set(groups_cfg.get("exclude_ages") or [])
    in_scope = [r for r in rows if r.age not in excluded]
    out_of_scope = [r for r in rows if r.age in excluded]
    if not in_scope:
        raise ValueError("no photos left after exclude_ages")

    attributes = {}
    for attribute in groups_cfg["attributes"]:
        groups = by_group(in_scope, attribute, gate)
        attributes[attribute] = {
            "groups": groups,
            "gaps": gaps(groups, groups_cfg["min_group_size"]),
        }
    candidates = [
        {**gap, "attribute": attribute}
        for attribute, result in attributes.items()
        for gap in result["gaps"]
    ]
    return {
        "photos": len(rows),
        "photos_in_scope": len(in_scope),
        "overall": group_metrics(in_scope, gate),
        "attributes": attributes,
        "excluded_ages": by_group(out_of_scope, "age", gate) if out_of_scope else {},
        "largest_gap": max(candidates, key=lambda c: c["gap"]) if candidates else None,
    }
