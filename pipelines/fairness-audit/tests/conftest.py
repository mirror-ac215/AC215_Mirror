"""Shared test setup: download the YuNet detector (pinned URL in params.yaml) if missing.

The model file is not committed. The download is checked against the sha256 in
params.yaml, and a file with another hash is deleted rather than used.
"""

import hashlib
import urllib.request
from pathlib import Path

import pytest
import yaml

PARAMS_PATH = Path(__file__).resolve().parents[1] / "params.yaml"


@pytest.fixture(scope="session", autouse=True)
def yunet_model_file() -> None:
    spec = yaml.safe_load(PARAMS_PATH.read_text())["detector"]
    path = (PARAMS_PATH.parent / spec["model"]).resolve()
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"]:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(spec["url"], timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != spec["sha256"]:
        raise RuntimeError("downloaded YuNet does not match the sha256 in params.yaml")
    path.write_bytes(data)
