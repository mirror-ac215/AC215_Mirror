#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir/.."

image_name="mirror-db-test"
container_name="mirror-db-test-$$"
database_name="mirror_test"
database_user="mirror_test"
database_password="test-only-password"

cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

run_sql() {
  docker exec -i "$container_name" \
    psql -X -v ON_ERROR_STOP=1 -U "$database_user" -d "$database_name" -tA -c "$1"
}

assert_equals() {
  local expected="$1"
  local actual="$2"
  local description="$3"

  if [[ "$actual" != "$expected" ]]; then
    echo "FAIL: $description. Expected '$expected', got '$actual'." >&2
    exit 1
  fi
}

docker build --tag "$image_name" .
docker run -d --name "$container_name" \
  -e "POSTGRES_DB=$database_name" \
  -e "POSTGRES_USER=$database_user" \
  -e "POSTGRES_PASSWORD=$database_password" \
  -e "MIRROR_DEMO_PASSWORD=$database_password" \
  "$image_name" >/dev/null

for _ in $(seq 1 30); do
  if docker exec "$container_name" \
    pg_isready -U "$database_user" -d "$database_name" >/dev/null 2>&1 \
    && [[ "$(docker inspect --format '{{.State.Health.Status}}' "$container_name")" == "healthy" ]]; then
    break
  fi
  sleep 1
done

assert_equals "healthy" "$(docker inspect --format '{{.State.Health.Status}}' "$container_name")" "container health"

assert_equals "6" "$(run_sql "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('users', 'patients', 'sessions', 'messages', 'emotion_windows', 'review_flags');")" "required tables"
assert_equals "2" "$(run_sql "SELECT count(*) FROM users WHERE role = 'clinician';")" "seeded clinician count"
assert_equals "5" "$(run_sql "SELECT count(*) FROM patients;")" "seeded patient count"
assert_equals "5" "$(run_sql "SELECT count(*) FROM patients p JOIN users u ON u.id = p.clinician_id WHERE u.role = 'clinician';")" "patient-to-clinician assignments"
assert_equals "t" "$(run_sql "SELECT to_regclass('public.raw_frames') IS NULL;")" "raw_frames table absence"

if run_sql "INSERT INTO users (email, display_name, role, password_hash) VALUES ('bad-role@example.test', 'Invalid Role', 'invalid', 'not-a-password-hash');" >/dev/null 2>&1; then
  echo "FAIL: invalid user role was accepted." >&2
  exit 1
fi

if run_sql "INSERT INTO messages (session_id, role, text) VALUES ('00000000-0000-0000-0000-000000000999', 'patient', 'orphan message');" >/dev/null 2>&1; then
  echo "FAIL: message with missing session was accepted." >&2
  exit 1
fi

if run_sql "INSERT INTO patients (user_id, clinician_id) VALUES ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000102');" >/dev/null 2>&1; then
  echo "FAIL: clinician user was accepted as a patient profile." >&2
  exit 1
fi

if run_sql "UPDATE patients SET clinician_id = '00000000-0000-0000-0000-000000000201' WHERE user_id = '00000000-0000-0000-0000-000000000202';" >/dev/null 2>&1; then
  echo "FAIL: patient user was accepted as a clinician assignment." >&2
  exit 1
fi

run_sql "INSERT INTO sessions (id, patient_id, camera_consent) VALUES ('00000000-0000-0000-0000-000000000301', '00000000-0000-0000-0000-000000000201', TRUE);" >/dev/null
run_sql "INSERT INTO messages (id, session_id, role, text) VALUES ('00000000-0000-0000-0000-000000000401', '00000000-0000-0000-0000-000000000301', 'patient', 'test message');" >/dev/null

if run_sql "INSERT INTO review_flags (patient_id, message_id) VALUES ('00000000-0000-0000-0000-000000000202', '00000000-0000-0000-0000-000000000401');" >/dev/null 2>&1; then
  echo "FAIL: cross-patient review flag was accepted." >&2
  exit 1
fi

if run_sql "INSERT INTO review_flags (patient_id, message_id, reviewed_at, reviewed_by) VALUES ('00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-000000000401', now(), '00000000-0000-0000-0000-000000000201');" >/dev/null 2>&1; then
  echo "FAIL: patient user was accepted as a review-flag reviewer." >&2
  exit 1
fi

run_sql "INSERT INTO review_flags (patient_id, message_id, reviewed_at, reviewed_by) VALUES ('00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-000000000401', now(), '00000000-0000-0000-0000-000000000101');" >/dev/null
assert_equals "crisis" "$(run_sql "SELECT reason FROM review_flags WHERE message_id = '00000000-0000-0000-0000-000000000401';")" "review flag reason defaults to crisis"

if run_sql "INSERT INTO review_flags (patient_id, message_id, reason) VALUES ('00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-000000000401', 'tired');" >/dev/null 2>&1; then
  echo "FAIL: an unknown review flag reason was accepted." >&2
  exit 1
fi

if run_sql "DELETE FROM messages WHERE id = '00000000-0000-0000-0000-000000000401';" >/dev/null 2>&1; then
  echo "FAIL: a flagged message was deleted without first removing its review flag." >&2
  exit 1
fi

if run_sql "INSERT INTO review_flags (patient_id, message_id, reviewed_at, reviewed_by) VALUES ('00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-000000000401', now(), '00000000-0000-0000-0000-000000000102');" >/dev/null 2>&1; then
  echo "FAIL: unassigned clinician was accepted as a review-flag reviewer." >&2
  exit 1
fi

if run_sql "UPDATE users SET role = 'patient' WHERE id = '00000000-0000-0000-0000-000000000101';" >/dev/null 2>&1; then
  echo "FAIL: role change broke an existing clinician assignment." >&2
  exit 1
fi

if run_sql "UPDATE users SET role = 'clinician' WHERE id = '00000000-0000-0000-0000-000000000201';" >/dev/null 2>&1; then
  echo "FAIL: role change broke an existing patient profile." >&2
  exit 1
fi


run_sql "INSERT INTO sessions (id, patient_id, camera_consent) VALUES ('00000000-0000-0000-0000-000000000302', '00000000-0000-0000-0000-000000000202', TRUE);" >/dev/null
if run_sql "UPDATE messages SET session_id = '00000000-0000-0000-0000-000000000302' WHERE id = '00000000-0000-0000-0000-000000000401';" >/dev/null 2>&1; then
  echo "FAIL: message reassignment broke an existing review flag." >&2
  exit 1
fi

if run_sql "UPDATE sessions SET patient_id = '00000000-0000-0000-0000-000000000202' WHERE id = '00000000-0000-0000-0000-000000000301';" >/dev/null 2>&1; then
  echo "FAIL: session ownership change broke an existing review flag." >&2
  exit 1
fi

run_sql "DELETE FROM users WHERE id = '00000000-0000-0000-0000-000000000201';" >/dev/null
assert_equals "0" "$(run_sql "SELECT count(*) FROM patients WHERE user_id = '00000000-0000-0000-0000-000000000201';")" "deleted patient profile"
assert_equals "0" "$(run_sql "SELECT count(*) FROM messages WHERE id = '00000000-0000-0000-0000-000000000401';")" "deleted patient message"
assert_equals "0" "$(run_sql "SELECT count(*) FROM review_flags WHERE message_id = '00000000-0000-0000-0000-000000000401';")" "deleted patient review flag"

echo "PASS: database schema, seeds, health check, and constraints verified."
