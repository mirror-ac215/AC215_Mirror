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
  -e LLM_FORCE_MODEL_DOWNLOAD="${LLM_FORCE_MODEL_DOWNLOAD:-1}" \
  llm-service -c '
import json
import os
from pathlib import Path

from huggingface_hub import snapshot_download
from safetensors import safe_open

model_name = os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-3B-Instruct")
force_download = os.environ.get("LLM_FORCE_MODEL_DOWNLOAD", "1") == "1"
model_path = Path(snapshot_download(
    repo_id=model_name,
    cache_dir="/root/.cache/huggingface",
    allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.py", "tokenizer*", "merges.txt", "vocab.*", "*.tiktoken"],
    force_download=force_download,
))

config_path = model_path / "config.json"
if not config_path.is_file():
    raise SystemExit("model artifact validation failed: config.json is missing")
json.loads(config_path.read_text())
shards = sorted(model_path.glob("*.safetensors"))
if not shards:
    raise SystemExit("model artifact validation failed: no safetensors weights were downloaded")
for shard in shards:
    with safe_open(shard, framework="pt") as handle:
        if not list(handle.keys()):
            raise SystemExit(f"model artifact validation failed: empty shard {shard.name}")
print(f"model artifact validation passed: {len(shards)} safetensors shard(s)")
'
