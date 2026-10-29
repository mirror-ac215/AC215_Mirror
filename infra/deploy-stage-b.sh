#!/usr/bin/env bash
# M3-14 Stage B deployment: pull immutable Artifact Registry images only.
set -euo pipefail

if [[ ! -f infra/.env.prod ]]; then
  printf 'Missing infra/.env.prod. Copy infra/.env.prod.example outside Git and fill host-only values.\n' >&2
  exit 64
fi

for command in docker git; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'Required command not found: %s\n' "$command" >&2
    exit 69
  }
done

set -a
# shellcheck disable=SC1091
source infra/.env.prod
set +a

for name in MIRROR_IMAGE_REGISTRY MIRROR_IMAGE_REPOSITORY MIRROR_IMAGE_TAG; do
  if [[ -z "${!name:-}" ]]; then
    printf 'Missing required M3-14 deployment value: %s\n' "$name" >&2
    exit 64
  fi
done

if [[ ! "$MIRROR_IMAGE_TAG" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'MIRROR_IMAGE_TAG must be the 40-character lowercase Git SHA published by CI.\n' >&2
  exit 64
fi

revision="$(git rev-parse HEAD)"
if [[ "$revision" != "$MIRROR_IMAGE_TAG" ]]; then
  printf 'Checked-out source revision (%s) does not match MIRROR_IMAGE_TAG (%s).\n' "$revision" "$MIRROR_IMAGE_TAG" >&2
  printf 'Check out the exact merged revision before deploying its immutable images.\n' >&2
  exit 65
fi

compose=(
  docker compose
  --env-file infra/.env.prod
  -f infra/compose.yml
  -f infra/compose.prod.yml
  -f infra/compose.registry.yml
)

"${compose[@]}" config --quiet
"${compose[@]}" pull
"${compose[@]}" up -d --no-build --wait --wait-timeout 600
"${compose[@]}" ps

printf '\nStage B deployment is running immutable Artifact Registry images tagged %s.\n' "$MIRROR_IMAGE_TAG"
printf 'Record the resolved image digests with: docker compose --env-file infra/.env.prod -f infra/compose.yml -f infra/compose.prod.yml -f infra/compose.registry.yml images\n'
