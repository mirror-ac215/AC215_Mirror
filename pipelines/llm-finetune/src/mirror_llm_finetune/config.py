"""Load and check params.yaml before anything expensive starts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

COMMIT = re.compile(r"[0-9a-f]{40}")


def load_params(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def problems(params: dict[str, Any], *, for_training: bool) -> list[str]:
    """Everything wrong with params: one run reports all problems at once."""
    found: list[str] = []
    revision = params["base_model"].get("revision") or ""
    if for_training and not COMMIT.fullmatch(revision):
        found.append("base_model.revision must be a full 40-character commit hash")
    lora = params["lora"]
    if lora["r"] <= 0 or lora["alpha"] <= 0 or not 0 <= lora["dropout"] < 1:
        found.append("lora: r and alpha must be positive and dropout in [0, 1)")
    if not params["system_prompt"].strip():
        found.append("system_prompt must not be empty")
    if not params["output"]["gcs_prefix"].startswith("gs://"):
        found.append("output.gcs_prefix must start with gs://")
    return found


def check(params: dict[str, Any], *, for_training: bool) -> None:
    found = problems(params, for_training=for_training)
    if found:
        raise ValueError("params.yaml: " + "; ".join(found))


def gcs_to_fuse(uri: str) -> str:
    """gs://bucket/path -> /gcs/bucket/path: Vertex AI mounts buckets there (Cloud Storage FUSE)."""
    if not uri.startswith("gs://"):
        return uri
    return "/gcs/" + uri.removeprefix("gs://")
