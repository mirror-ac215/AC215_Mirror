#!/usr/bin/env bash
# Download and validate the public base model in the persistent Compose cache
# before vLLM starts. This script never handles a Hugging Face token or adapter.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f infra/.env.prod ]]; then
  printf 'Missing infra/.env.prod. Copy infra/.env.prod.example outside Git and fill host-only values.\n' >&2
  exit 64
fi

set -a
# shellcheck disable=SC1091
source infra/.env.prod
set +a

compose=(
  docker compose
  --env-file infra/.env.prod
  -f infra/compose.yml
  -f infra/compose.prod.yml
  -f infra/compose.registry.yml
)

"${compose[@]}" run --rm --no-deps --entrypoint python3 \
  -e HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}" \
  -e LLM_FORCE_MODEL_DOWNLOAD="${LLM_FORCE_MODEL_DOWNLOAD:-0}" \
  llm-service -c '
import hashlib
import json
import os
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download
from safetensors import safe_open

model_name = os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-3B-Instruct")
force_download = os.environ.get("LLM_FORCE_MODEL_DOWNLOAD", "0") == "1"
# Do not set cache_dir: vLLM reads the standard Hugging Face hub cache too.
model_path = Path(snapshot_download(repo_id=model_name, force_download=force_download))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bad_shards(path: Path) -> list[Path]:
    invalid: list[Path] = []
    for shard in sorted(path.glob("*.safetensors")):
        # A Hugging Face LFS snapshot points at a blob named by its SHA-256.
        if shard.resolve().name != sha256(shard):
            invalid.append(shard)
    return invalid


config_path = model_path / "config.json"
if not config_path.is_file():
    raise SystemExit("model artifact validation failed: config.json is missing")
json.loads(config_path.read_text())
shards = sorted(model_path.glob("*.safetensors"))
if not shards:
    raise SystemExit("model artifact validation failed: no safetensors weights were downloaded")
invalid = bad_shards(model_path)
for shard in invalid:
    hf_hub_download(repo_id=model_name, filename=str(shard.relative_to(model_path)), force_download=True)
if invalid:
    model_path = Path(snapshot_download(repo_id=model_name))
    invalid = bad_shards(model_path)
if invalid:
    names = ", ".join(shard.name for shard in invalid)
    raise SystemExit(f"model artifact validation failed after shard repair: {names}")
for shard in shards:
    with safe_open(shard, framework="pt") as handle:
        if not list(handle.keys()):
            raise SystemExit(f"model artifact validation failed: empty shard {shard.name}")
print(f"model artifact validation passed: {len(shards)} safetensors shard(s)")
'
