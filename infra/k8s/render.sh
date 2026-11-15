#!/usr/bin/env bash
# Render a non-secret, immutable-image manifest bundle. This script never calls
# kubectl, gcloud, or a cloud API; Mostafa owns all later cluster operations.
set -euo pipefail

readonly REQUIRED_VARS=(
  MIRROR_IMAGE_REGISTRY
  MIRROR_IMAGE_REPOSITORY
  MIRROR_IMAGE_TAG
  MIRROR_DOMAIN
  MIRROR_CV_GSA
  MIRROR_CV_MODEL_BUCKET
  MIRROR_CV_MODEL_OBJECT
  MIRROR_CV_MODEL_VERSION
)
for name in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    printf 'Missing required non-secret input: %s\n' "$name" >&2
    exit 2
  fi
done
if [[ ! "$MIRROR_IMAGE_TAG" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'MIRROR_IMAGE_TAG must be a 40-character accepted-main SHA.\n' >&2
  exit 2
fi
: "${OUTPUT:=./mirror-gke-rendered.yaml}"

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
cp -R "$script_dir"/. "$work_dir"

export "${REQUIRED_VARS[@]}"
python3 - "$work_dir" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
names = (
    "MIRROR_IMAGE_REGISTRY",
    "MIRROR_IMAGE_REPOSITORY",
    "MIRROR_IMAGE_TAG",
    "MIRROR_DOMAIN",
    "MIRROR_CV_GSA",
    "MIRROR_CV_MODEL_BUCKET",
    "MIRROR_CV_MODEL_OBJECT",
    "MIRROR_CV_MODEL_VERSION",
)
for manifest in root.glob("*.yaml"):
    content = manifest.read_text(encoding="utf-8")
    for name in names:
        content = content.replace("${" + name + "}", os.environ[name])
    manifest.write_text(content, encoding="utf-8")
PY

kustomize build "$work_dir" > "$OUTPUT"
printf 'Rendered non-secret manifest bundle: %s\n' "$OUTPUT"
