#!/usr/bin/env bash
# M3-14 Stage B deployment: pull immutable Artifact Registry images only.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f infra/.env.prod ]]; then
  printf 'Missing infra/.env.prod. Copy infra/.env.prod.example outside Git and fill host-only values.\n' >&2
  exit 64
fi

for command in docker git gcloud curl python3; do
  command -v "$command" >/dev/null 2>&1 || {
    printf 'Required command not found: %s\n' "$command" >&2
    exit 69
  }
done

set -a
# shellcheck disable=SC1091
source infra/.env.prod
set +a

# Keep these defaults paired with the production cv-service configuration.
# The preflight below obtains a token from the VM metadata server directly,
# rather than from a gcloud user login or credential-file fallback.
CV_MODEL_BUCKET="${CV_MODEL_BUCKET:-mirror-ac215-data}"
CV_MODEL_OBJECT="${CV_MODEL_OBJECT:-models/cv/v4/vit_b16_v4.pth}"

for name in MIRROR_IMAGE_REGISTRY MIRROR_IMAGE_REPOSITORY MIRROR_IMAGE_TAG; do
  if [[ -z "${!name:-}" ]]; then
    printf 'Missing required M3-14 deployment value: %s\n' "$name" >&2
    exit 64
  fi
done

if [[ ! "$MIRROR_IMAGE_REGISTRY" =~ ^[a-z0-9-]+-docker\.pkg\.dev$ ]]; then
  printf 'MIRROR_IMAGE_REGISTRY must be an Artifact Registry host, such as us-central1-docker.pkg.dev.\n' >&2
  exit 64
fi

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

if ! metadata_token="$(
  curl --fail --silent --show-error \
    --header 'Metadata-Flavor: Google' \
    'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token' |
  python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])'
)"; then
  printf 'CV model access preflight failed: unable to obtain the attached VM identity token.\n' >&2
  exit 66
fi

encoded_cv_object="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$CV_MODEL_OBJECT")"
if ! curl --fail --silent --show-error \
  --header "Authorization: Bearer ${metadata_token}" \
  "https://storage.googleapis.com/storage/v1/b/${CV_MODEL_BUCKET}/o/${encoded_cv_object}" >/dev/null; then
  printf 'CV model access preflight failed for gs://%s/%s.\n' "$CV_MODEL_BUCKET" "$CV_MODEL_OBJECT" >&2
  printf 'Grant the configured VM service account roles/storage.objectViewer on the reviewed model bucket, then retry.\n' >&2
  exit 66
fi

# The gcplogs driver refuses to start a container it cannot log for, so check this first.
vm_project="$(curl --fail --silent --show-error --header 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/project/project-id')"
if ! curl --fail --silent --show-error --request POST \
  --header "Authorization: Bearer ${metadata_token}" \
  --header 'Content-Type: application/json' \
  --data "{\"logName\":\"projects/${vm_project}/logs/mirror-deploy-preflight\",\"resource\":{\"type\":\"global\"},\"entries\":[{\"severity\":\"INFO\",\"textPayload\":\"deploy preflight\"}]}" \
  'https://logging.googleapis.com/v2/entries:write' >/dev/null; then
  printf 'Cloud Logging preflight failed for project %s.\n' "$vm_project" >&2
  printf 'Grant the configured VM service account roles/logging.logWriter, then retry.\n' >&2
  exit 66
fi

gcloud auth configure-docker "$MIRROR_IMAGE_REGISTRY" --quiet
"${compose[@]}" config --quiet
"${compose[@]}" pull
# This validates the existing Hugging Face cache and selectively repairs a
# mismatched safetensors shard before vLLM starts.
bash infra/prepare-llm-model.sh
"${compose[@]}" up -d --no-build --wait --wait-timeout 600
"${compose[@]}" ps

"${compose[@]}" exec -T llm-service python3 -c '
import json
import urllib.request

request = urllib.request.Request(
    "http://localhost:8002/v1/chat/completions",
    data=json.dumps({
        "model": "mirror-persona-v1",
        "messages": [{"role": "user", "content": "Reply with the single word READY."}],
        "max_tokens": 8,
        "temperature": 0,
    }).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=120) as response:
    payload = json.load(response)
text = payload["choices"][0]["message"]["content"]
if not isinstance(text, str) or not text.strip() or len(text) > 1024:
    raise SystemExit("llm smoke response was empty or implausibly large")
if "ready" not in text.lower():
    raise SystemExit("llm smoke response did not contain the expected READY token")
if sum(character.isprintable() or character.isspace() for character in text) / len(text) < 0.95:
    raise SystemExit("llm smoke response contained non-printable output")
print(f"llm smoke response: {text!r}")
'

printf '\nStage B deployment is running immutable Artifact Registry images tagged %s.\n' "$MIRROR_IMAGE_TAG"
printf 'Record the resolved image digests with: docker compose --env-file infra/.env.prod -f infra/compose.yml -f infra/compose.prod.yml -f infra/compose.registry.yml images\n'
