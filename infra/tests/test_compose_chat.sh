#!/usr/bin/env bash
# Exercise the normal and crisis chat paths against the running Compose Postgres.
# The CI job starts the default mock-LLM stack before invoking this script.
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

# Real login: the gateway no longer accepts any fixed dev/demo bearer
# token, so obtain a short-lived JWT the same way the frontend does.
# Same default as infra/compose.yml, so a run with no infra/.env logs in too.
MIRROR_DEMO_PASSWORD="${MIRROR_DEMO_PASSWORD:-local-demo-password}"
login_payload=$(curl -fsS -H 'Content-Type: application/json' \
  -d "{\"email\":\"patient.alex@example.test\",\"password\":\"${MIRROR_DEMO_PASSWORD}\"}" \
  "$gateway_url/auth/login")
access_token=$(python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])' <<<"$login_payload")
auth=(-H "Authorization: Bearer ${access_token}")

new_session() {
  local payload
  payload=$(curl -fsS "${auth[@]}" -H 'Content-Type: application/json' \
    -d '{"camera_consent":false}' "$gateway_url/sessions")
  python3 -c 'import json, sys; print(json.load(sys.stdin)["session_id"])' <<<"$payload"
}

ordinary_session=$(new_session)
ordinary=$(curl -fsSN "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"text":"Today was hard"}' "$gateway_url/sessions/${ordinary_session}/messages")
grep -q 'event: done' <<<"$ordinary"

crisis_session=$(new_session)
crisis=$(curl -fsSN "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"text":"I want to die"}' "$gateway_url/sessions/${crisis_session}/messages")
grep -q 'event: crisis' <<<"$crisis"
grep -q '988' <<<"$crisis"
grep -q '"review_flag_created": true' <<<"$crisis"

# Query only row counts, never patient text, to prove the session/message/flag
# inserts used the running Compose database rather than the in-process fake.
# Counts are scoped to Alex: the seeded demo history (services/db/demo-history.sql)
# belongs to other patients and must not make these checks pass on its own.
alex="00000000-0000-0000-0000-000000000201"
sessions=$("${compose[@]}" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"SELECT count(*) FROM sessions WHERE patient_id = '${alex}'\"")
messages=$("${compose[@]}" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"SELECT count(*) FROM messages m JOIN sessions s ON s.id = m.session_id WHERE s.patient_id = '${alex}'\"")
flags=$("${compose[@]}" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"SELECT count(*) FROM review_flags WHERE patient_id = '${alex}'\"")
test "$sessions" -ge 2
test "$messages" -ge 3
test "$flags" -ge 1

# M4-03: clinician-only aggregate views and flag acknowledgement use the same
# real Postgres rows. Never echo patient messages or raw frames in this smoke test.
clinician_login=$(curl -fsS -H 'Content-Type: application/json' \
  -d "{\"email\":\"clinician.ada@example.test\",\"password\":\"${MIRROR_DEMO_PASSWORD}\"}" \
  "$gateway_url/auth/login")
clinician_token=$(python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])' <<<"$clinician_login")
clinician_auth=(-H "Authorization: Bearer ${clinician_token}")

patients=$(curl -fsS "${clinician_auth[@]}" "$gateway_url/clinician/patients")
python3 -c 'import json, sys; rows=json.load(sys.stdin); assert rows and all({"patient_id", "display_name", "last_session_at", "needs_review"} <= set(row) for row in rows)' <<<"$patients"

trend=$(curl -fsS "${clinician_auth[@]}" "$gateway_url/clinician/patients/00000000-0000-0000-0000-000000000201/trend")
python3 -c 'import json, sys; rows=json.load(sys.stdin); assert rows and all("session_id" not in row and "text" not in row for row in rows)' <<<"$trend"

patient_status=$(curl -sS -o /dev/null -w '%{http_code}' "${auth[@]}" "$gateway_url/clinician/patients")
test "$patient_status" = 403

flag_id=$("${compose[@]}" exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT id FROM review_flags WHERE patient_id = '\''00000000-0000-0000-0000-000000000201'\'' AND reviewed_at IS NULL LIMIT 1"')
test -n "$flag_id"
acknowledged=$(curl -fsS -X PATCH "${clinician_auth[@]}" -H 'Content-Type: application/json' \
  -d '{"reviewed":true}' "${gateway_url}/clinician/review-flags/${flag_id}")
test "$acknowledged" = '{"reviewed":true}'
reviewed_by=$("${compose[@]}" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"SELECT reviewed_by FROM review_flags WHERE id = '${flag_id}'\"")
test "$reviewed_by" = '00000000-0000-0000-0000-000000000101'