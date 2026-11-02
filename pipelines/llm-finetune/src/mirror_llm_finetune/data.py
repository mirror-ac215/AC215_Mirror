"""Persona pairs (M2-09 output) -> chat examples for supervised fine-tuning.

Each example is in TRL's prompt-completion chat format: the loss is computed on
the completion (Mirror's reply) only, never on the system prompt or the
patient's message.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

COLUMNS = {"pair_id", "prompt", "response"}
SPLITS = ("train", "val", "test")


def read_split(data_dir: Path, split: str) -> list[dict[str, str]]:
    path = data_dir / f"{split}.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing columns {sorted(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path} has no rows (did you run `dvc repro persona_clean`?)")
    return rows


def to_example(row: dict[str, str], system_prompt: str) -> dict[str, Any]:
    return {
        "prompt": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": row["prompt"]},
        ],
        "completion": [{"role": "assistant", "content": row["response"]}],
    }


def fingerprint(data_dir: Path) -> str:
    """sha256 over the three split files: logged with the adapter; every adapter
    thus names the exact data it was trained on (data versioning)."""
    digest = hashlib.sha256()
    for split in SPLITS:
        digest.update((data_dir / f"{split}.csv").read_bytes())
    return digest.hexdigest()
