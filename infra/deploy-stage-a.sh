#!/usr/bin/env bash
# Manual M3-13 Stage A deployment. M3-14 later replaces local builds with
# immutable Artifact Registry image tags; do not claim that capability here.
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

if ! nvidia-smi >/dev/null 2>&1; then
  printf 'The host NVIDIA driver is unavailable; run infra/gcp/bootstrap-vm.sh first.\n' >&2
  exit 69
fi

revision="$(git rev-parse HEAD)"
printf 'Deploying reviewed source revision %s\n' "$revision"

docker compose --env-file infra/.env.prod \
  -f infra/compose.yml -f infra/compose.prod.yml config --quiet

docker compose --env-file infra/.env.prod \
  -f infra/compose.yml -f infra/compose.prod.yml up -d --build --wait --wait-timeout 600

docker compose --env-file infra/.env.prod \
  -f infra/compose.yml -f infra/compose.prod.yml ps

printf '\nStage A deployment started. Verify externally after DNS propagates:\n'
printf '  curl -fsSI http://<domain>\n'
printf '  curl -fsS https://<domain>/health\n'
printf '  curl -fsS https://<domain>/api/health\n'
printf '\nRecord this source revision in the deployment notes: %s\n' "$revision"
