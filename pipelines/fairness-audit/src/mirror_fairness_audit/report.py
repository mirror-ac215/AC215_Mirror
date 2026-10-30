"""The audit as report.json (for the model card) and report.md (for people)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mirror_fairness_audit import LABELS

DESCRIBE = {
    "face_found": "the face detector finding a face",
    "gate_ok": "a trusted camera reading (face found and gate passed)",
    "gate_ok_if_face": "the gate passing when a face is found",
    "confidence": "mean confidence (top probability)",
    "share_negative": "being read as negative (angry, disgust, fear or sad)",
    **{f"share_{label}": f"being read as {label}" for label in LABELS},
}
KEY_METRICS = ("face_found", "gate_ok", "share_negative", "share_happy", "confidence")


def pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def headline(result: dict[str, Any]) -> str:
    gap = result["largest_gap"]
    if gap is None:
        return "No gap could be measured: fewer than two groups reach min_group_size."
    noise = (
        "larger than the noise in either group (95% intervals do not overlap)"
        if gap["separated"]
        else "within the noise of the two groups (95% intervals overlap)"
    )
    return (
        f"Largest gap: {DESCRIBE[gap['metric']]}, by {gap['attribute']}: "
        f"{gap['high_group']} {pct(gap['high'])} vs {gap['low_group']} {pct(gap['low'])}, "
        f"a gap of {100 * gap['gap']:.1f} points, {noise}."
    )


def _table(groups: dict[str, Any], metrics: tuple[str, ...]) -> list[str]:
    head = "| Group | Photos | " + " | ".join(metrics) + " |"
    lines = [head, "|" + "---|" * (len(metrics) + 2)]
    for name, group in groups.items():
        cells = [pct(group["metrics"][m]["value"]) for m in metrics]
        lines.append(f"| {name} | {group['n']} | " + " | ".join(cells) + " |")
    return lines


def markdown(result: dict[str, Any], params: dict[str, Any], meta: dict[str, Any]) -> str:
    shares = tuple(f"share_{label}" for label in LABELS)
    lines = [
        "# M3-02 fairness audit",
        "",
        f"**{headline(result)}**",
        "",
        (
            f"Model `{params['model']['version']}`, data {params['data']['name']} "
            f"(`{params['data']['version']}`). {result['photos_in_scope']} of {result['photos']} "
            f"photos in scope; ages {', '.join(params['groups']['exclude_ages']) or 'none'} reported "
            "separately. Gaps name only groups with at least "
            f"{params['groups']['min_group_size']} photos."
        ),
        "",
        (
            "FairFace has no expression labels: these numbers show how differently the model "
            "behaves per group, not how accurate it is."
        ),
        "",
        "## Key gaps",
        "",
        "| Attribute | Measure | Highest | Lowest | Gap (points) | Beyond noise |",
        "|---|---|---|---|---|---|",
    ]
    for attribute, data in result["attributes"].items():
        for gap in data["gaps"]:
            if gap["metric"] in KEY_METRICS:
                lines.append(
                    f"| {attribute} | {DESCRIBE[gap['metric']]} | "
                    f"{gap['high_group']} {pct(gap['high'])} | {gap['low_group']} {pct(gap['low'])} | "
                    f"{100 * gap['gap']:.1f} | {'yes' if gap['separated'] else 'no'} |"
                )
    for attribute, data in result["attributes"].items():
        lines += ["", f"## By {attribute}", ""]
        lines += _table(data["groups"], KEY_METRICS)
        lines += ["", "Top emotion per group:", ""]
        lines += _table(data["groups"], shares)
    if result["excluded_ages"]:
        lines += ["", "## Children (out of scope, for reference)", ""]
        lines += _table(result["excluded_ages"], KEY_METRICS)
    lines += [
        "",
        "## Provenance",
        "",
        f"- checkpoint sha256: `{meta.get('checkpoint_sha256', 'unknown')}`",
        f"- labels sha256: `{meta.get('labels_sha256', 'unknown')}`",
        f"- predictions sha256: `{meta.get('predictions_sha256', 'unknown')}`",
        f"- code: `{meta.get('code_revision', 'unknown')}`",
        f"- gate: top >= {params['gate']['min_top_prob']}, margin >= {params['gate']['min_margin']}",
        "",
    ]
    return "\n".join(lines)


def write(result: dict[str, Any], params: dict[str, Any], meta: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    payload = {"headline": headline(result), "params": params, "provenance": meta, **result}
    (out / "report.json").write_text(json.dumps(payload, indent=2) + "\n")
    (out / "report.md").write_text(markdown(result, params, meta))
