#!/usr/bin/env bash
# M4-04: the fallback paths against the real Compose stack.
# Runs after test_compose_chat.sh on the default stack (mock LLM, no cv-service):
#   - cv-service unavailable: a camera frame gets 503, and chat still answers text-only;
#   - llm-service stopped: chat still ends with the gentle reply, a done event and a saved row.
# It restarts llm-service before exiting, even on failure. Never echoes patient text.
set -euo pipefail

compose=(docker compose)
if [[ -n "${MIRROR_COMPOSE_PROJECT:-}" ]]; then
  compose+=(--project-name "$MIRROR_COMPOSE_PROJECT")
fi
compose+=(-f infra/compose.yml)
if [[ -n "${MIRROR_COMPOSE_PROJECT:-}" ]]; then
  if [[ -z "${MIRROR_GATEWAY_URL:-}" ]]; then
    echo 'MIRROR_GATEWAY_URL must be explicit when MIRROR_COMPOSE_PROJECT is set' >&2
    exit 2
  fi
  case "$MIRROR_GATEWAY_URL" in
    http://localhost:*|http://127.0.0.1:*|https://localhost:*|https://127.0.0.1:*) ;;
    *)
      echo 'MIRROR_GATEWAY_URL must use a loopback host for a named Compose project' >&2
      exit 2
      ;;
  esac
fi
gateway_url="${MIRROR_GATEWAY_URL:-http://localhost:8000}"
case "$gateway_url" in
  http://*|https://*) ;;
  *)
    echo 'MIRROR_GATEWAY_URL must be an http(s) URL' >&2
    exit 2
    ;;
esac


MIRROR_DEMO_PASSWORD="${MIRROR_DEMO_PASSWORD:-local-demo-password}"
login_payload=$(curl -fsS -H 'Content-Type: application/json' \
  -d "{\"email\":\"patient.alex@example.test\",\"password\":\"${MIRROR_DEMO_PASSWORD}\"}" \
  "$gateway_url/auth/login")
access_token=$(python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])' <<<"$login_payload")
auth=(-H "Authorization: Bearer ${access_token}")

new_session() {
  python3 -c 'import json, sys; print(json.load(sys.stdin)["session_id"])' <<<"$(
    curl -fsS "${auth[@]}" -H 'Content-Type: application/json' \
      -d "{\"camera_consent\":$1}" "$gateway_url/sessions")"
}

# Prints the last SSE event's name and its context.visual.status, e.g. "done dropped".
last_event() {
  python3 -c '
import json, sys
blocks = [b for b in sys.stdin.read().strip().split("\n\n") if b]
name, data = blocks[-1].split("\n")
payload = json.loads(data.removeprefix("data: "))
status = (payload.get("context") or {}).get("visual", {}).get("status", "-")
print(name.removeprefix("event: "), status)'
}

reply_of() {
  python3 -c '
import json, sys
print("".join(json.loads(b.split("\n")[1].removeprefix("data: "))["text"]
              for b in sys.stdin.read().strip().split("\n\n") if b.startswith("event: token")))'
}

fallback_count() {
  curl -fsS "$gateway_url/metrics" | python3 -c '
import sys
reason = sys.argv[1]
for line in sys.stdin:
    if line.startswith("mirror_gateway_fallback_total{") and f"reason=\"{reason}\"" in line:
        print(int(float(line.rsplit(" ", 1)[1]))); break
else:
    print(0)' "$1"
}

# 1. cv-service unavailable (it is opt-in, so the default stack has none).
if "${compose[@]}" ps --services --status running | grep -qx cv-service; then
  echo "SKIP cv-service is running in this stack; the CV-down path is covered by unit tests"
else
  cv_before=$(fallback_count cv_unavailable)
  camera_session=$(new_session true)
  frame_status=$(printf '\xff\xd8\xff\xd9' | curl -sS -o /dev/null -w '%{http_code}' "${auth[@]}" \
    -F 'image=@-;filename=frame.jpg;type=image/jpeg' "$gateway_url/sessions/${camera_session}/frames")
  test "$frame_status" = 503
  turn=$(curl -fsSN "${auth[@]}" -H 'Content-Type: application/json' \
    -d '{"text":"Long day at work"}' "$gateway_url/sessions/${camera_session}/messages")
  test "$(last_event <<<"$turn")" = "done dropped"
  test "$(fallback_count cv_unavailable)" -gt "$cv_before"
  echo "PASS cv-service down: frame 503, chat answered text-only (visual status dropped)"
fi

# 2. llm-service stopped: the gateway must still finish the turn.
restart_llm() {
  "${compose[@]}" up -d --no-build --wait --wait-timeout 120 llm-service >/dev/null
}
trap restart_llm EXIT
"${compose[@]}" stop llm-service >/dev/null
llm_before=$(fallback_count llm_unavailable)
text_session=$(new_session false)
turn=$(curl -fsSN "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"text":"I had a quiet afternoon"}' "$gateway_url/sessions/${text_session}/messages")
test "$(last_event <<<"$turn")" = "done camera_off"
grep -q "having trouble finding my words" <<<"$(reply_of <<<"$turn")"
test "$(fallback_count llm_unavailable)" -gt "$llm_before"
saved=$("${compose[@]}" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"SELECT count(*) FROM messages WHERE session_id = '${text_session}' AND role = 'assistant'\"")
test "$saved" = 1
echo "PASS llm-service down: gentle reply, done event, reply saved"

restart_llm
trap - EXIT
curl -fsS "$gateway_url/health" | grep -q '"llm-service":"ok"'
echo "PASS llm-service restarted and healthy"
