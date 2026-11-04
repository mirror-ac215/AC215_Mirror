#!/usr/bin/env bash
# Exercise the normal and crisis chat paths against the running Compose Postgres.
# The CI job starts the default mock-LLM stack before invoking this script.
set -euo pipefail

compose=(docker compose -f infra/compose.yml)
auth=(-H 'Authorization: Bearer dev-patient-token')

new_session() {
  local payload
  payload=$(curl -fsS "${auth[@]}" -H 'Content-Type: application/json' \
    -d '{"camera_consent":false}' http://localhost:8000/sessions)
  python3 -c 'import json, sys; print(json.load(sys.stdin)["session_id"])' <<<"$payload"
}

ordinary_session=$(new_session)
ordinary=$(curl -fsSN "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"text":"Today was hard"}' "http://localhost:8000/sessions/${ordinary_session}/messages")
grep -q 'event: done' <<<"$ordinary"

crisis_session=$(new_session)
crisis=$(curl -fsSN "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"text":"I want to die"}' "http://localhost:8000/sessions/${crisis_session}/messages")
grep -q 'event: crisis' <<<"$crisis"
grep -q '988' <<<"$crisis"
grep -q '"review_flag_created": true' <<<"$crisis"

# Query only row counts, never patient text, to prove the session/message/flag
# inserts used the running Compose database rather than the in-process fake.
sessions=$(${compose[@]} exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM sessions"')
messages=$(${compose[@]} exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM messages"')
flags=$(${compose[@]} exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM review_flags"')
test "$sessions" -ge 2
test "$messages" -ge 3
test "$flags" -ge 1