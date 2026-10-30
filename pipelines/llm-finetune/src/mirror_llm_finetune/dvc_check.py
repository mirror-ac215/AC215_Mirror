"""Before `submit` fingerprints the persona data: is it the current, unmodified DVC output?

`dvc status` compares the files on disk with the hashes in dvc.lock. An empty
result means the data is exactly what `dvc repro persona_clean` last produced
and recorded; anything else (a stale pull, an edited CSV, changed cleaning code)
stops the submission before a paid GPU job starts.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

STAGE = "persona_clean"  # dvc.yaml stage that produces data/processed/persona/v1 (M2-09)


def dvc_changes(repo_root: Path, stage: str = STAGE) -> dict[str, Any]:
    """`dvc status --json <stage>` run in the repo root: {} when data and dvc.lock agree."""
    try:
        result = subprocess.run(
            ["dvc", "status", "--json", stage],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as err:
        raise RuntimeError("dvc is not installed: uv tool install --with dvc-gs dvc") from err
    if result.returncode != 0:
        raise RuntimeError(f"`dvc status {stage}` failed in {repo_root}: {result.stderr.strip()}")
    return json.loads(result.stdout or "{}")


def require_clean(
    repo_root: Path,
    stage: str = STAGE,
    status: Callable[[Path, str], dict[str, Any]] | None = None,
) -> None:
    """Raise unless the stage's outputs match dvc.lock (`dvc status` is clean)."""
    changes = (status or dvc_changes)(repo_root, stage)
    if changes:
        raise ValueError(
            f"the persona data is not the current DVC version ({json.dumps(changes)}). "
            f"Run `dvc pull` and `dvc repro {stage}` from the repo root until `dvc status` "
            "is clean, then submit again"
        )
