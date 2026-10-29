"""IEMOCAP -> one row per utterance: transcript, consensus emotion, Mirror label.

Reads only the small text files of the release (EmoEvaluation and transcriptions),
streaming them straight out of the .tar.gz; the videos stay untouched. Utterances
whose label has no Mirror equivalent are dropped and counted in report.json.
Same inputs + same params.yaml => byte-identical outputs.

The output holds IEMOCAP transcripts: it lives in the private bucket via DVC only
(licence: non-commercial use, no redistribution) and is never committed to git.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import tarfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIELDS = [
    "utterance_id", "session", "dialog", "speaker", "kind", "start_s", "end_s",
    "iemocap_label", "label", "valence", "arousal", "dominance", "text",
]

# Session1/dialog/EmoEvaluation/Ses01F_impro01.txt and .../transcriptions/Ses01F_impro01.txt;
# "._" files are macOS metadata copies inside the archive and are skipped.
TEXT_FILE = re.compile(r"Session\d/dialog/(EmoEvaluation|transcriptions)/(?!\._)[^/]+\.txt$")

# "[6.2901 - 8.2357]<TAB>Ses01F_impro01_F000<TAB>neu<TAB>[2.5000, 2.5000, 2.5000]"
EVALUATION_LINE = re.compile(
    r"^\[(?P<start>\d+\.\d+) - (?P<end>\d+\.\d+)\]\s+(?P<id>Ses\S+)\s+(?P<code>\w+)\s+"
    r"\[(?P<v>\d+\.\d+), (?P<a>\d+\.\d+), (?P<d>\d+\.\d+)\]"
)

# "Ses01F_impro01_F000 [006.2901-008.2357]: Excuse me."
TRANSCRIPT_LINE = re.compile(r"^(?P<id>Ses\S+) \[[\d.]+-[\d.]+\]:\s?(?P<text>.*)$")


@dataclass(frozen=True)
class Evaluation:
    utterance_id: str
    start_s: float
    end_s: float
    code: str
    valence: float
    arousal: float
    dominance: float


def iter_text_files(source: Path) -> Iterator[tuple[str, str]]:
    """Yield (path inside the release, file text) for every label and transcript file.

    `source` is the release .tar.gz (read in one streaming pass, never unpacked)
    or an already extracted folder.
    """
    if source.is_dir():
        for path in sorted(source.rglob("*.txt")):
            name = path.relative_to(source).as_posix()
            if TEXT_FILE.search(name):
                yield name, path.read_text(encoding="utf-8", errors="replace")
        return
    if not source.exists():
        raise FileNotFoundError(f"{source} not found (did you run dvc pull?)")
    with tarfile.open(source, mode="r|gz") as archive:
        for member in archive:
            if member.isfile() and TEXT_FILE.search(member.name):
                handle = archive.extractfile(member)
                if handle is not None:
                    yield member.name, handle.read().decode("utf-8", errors="replace")


def parse_evaluation(text: str) -> list[Evaluation]:
    """The consensus label of each utterance; annotator detail lines are ignored."""
    rows = []
    for line in text.splitlines():
        match = EVALUATION_LINE.match(line.strip())
        if match:
            rows.append(Evaluation(
                match["id"], float(match["start"]), float(match["end"]), match["code"],
                float(match["v"]), float(match["a"]), float(match["d"]),
            ))
    return rows


def parse_transcription(text: str) -> dict[str, str]:
    """utterance_id -> transcript. Lines that are not utterances (no Ses... id) are skipped."""
    out = {}
    for line in text.splitlines():
        match = TRANSCRIPT_LINE.match(line.strip())
        if match:
            out[match["id"]] = " ".join(match["text"].split())
    return out


def describe(utterance_id: str) -> dict[str, str]:
    """Ses01F_impro01_F000 -> session 1, dialog Ses01F_impro01, speaker F, kind improvised."""
    dialog, turn = utterance_id.rsplit("_", 1)
    return {
        "session": str(int(utterance_id[3:5])),
        "dialog": dialog,
        "speaker": turn[0],
        "kind": "improvised" if "_impro" in dialog else "scripted",
    }


def build(source: Path, label_map: dict[str, str]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Join labels with transcripts and map labels. Returns (rows, counts for the report)."""
    evaluations: list[Evaluation] = []
    transcripts: dict[str, str] = {}
    files = Counter()
    for name, text in iter_text_files(source):
        if "/EmoEvaluation/" in name:
            evaluations.extend(parse_evaluation(text))
            files["EmoEvaluation"] += 1
        else:
            transcripts.update(parse_transcription(text))
            files["transcriptions"] += 1
    if not evaluations:
        raise ValueError(f"no EmoEvaluation labels found in {source}; is this the IEMOCAP release?")

    rows: list[dict[str, str]] = []
    dropped = Counter()
    for ev in sorted(evaluations, key=lambda e: e.utterance_id):
        text = transcripts.get(ev.utterance_id, "")
        if ev.code not in label_map:
            dropped[f"label:{ev.code}"] += 1
        elif not text:
            dropped["no_transcript"] += 1
        else:
            rows.append({
                "utterance_id": ev.utterance_id, **describe(ev.utterance_id),
                "start_s": f"{ev.start_s:.4f}", "end_s": f"{ev.end_s:.4f}",
                "iemocap_label": ev.code, "label": label_map[ev.code],
                "valence": f"{ev.valence:.4f}", "arousal": f"{ev.arousal:.4f}",
                "dominance": f"{ev.dominance:.4f}", "text": text,
            })
    counts = {
        "files_read": dict(sorted(files.items())),
        "utterances_labelled": len(evaluations),
        "iemocap_labels": dict(sorted(Counter(e.code for e in evaluations).items())),
        "dropped": dict(sorted(dropped.items())),
    }
    return rows, counts


def run(source: Path, out_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
    """Write utterances.csv and report.json to out_dir and return the report."""
    rows, counts = build(source, params["labels"])
    out_dir.mkdir(parents=True, exist_ok=True)
    table = out_dir / "utterances.csv"
    with table.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    report = {
        **counts,
        "utterances_kept": len(rows),
        "labels_kept": dict(sorted(Counter(r["label"] for r in rows).items())),
        "per_session": dict(sorted(Counter(r["session"] for r in rows).items())),
        "label_map": dict(sorted(params["labels"].items())),
        "utterances_sha256": hashlib.sha256(table.read_bytes()).hexdigest(),
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
