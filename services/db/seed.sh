#!/usr/bin/env sh
set -eu

if [ -z "${MIRROR_DEMO_PASSWORD:-}" ]; then
    echo "MIRROR_DEMO_PASSWORD must be set to initialize local demo accounts." >&2
    exit 1
fi

psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set=demo_password="$MIRROR_DEMO_PASSWORD" <<'SQL'
INSERT INTO users (id, email, display_name, role, password_hash) VALUES
    ('00000000-0000-0000-0000-000000000101', 'clinician.ada@example.test', 'Dr. Ada Chen', 'clinician', crypt(:'demo_password', gen_salt('bf', 12))),
    ('00000000-0000-0000-0000-000000000102', 'clinician.luis@example.test', 'Dr. Luis Morgan', 'clinician', crypt(:'demo_password', gen_salt('bf', 12))),
    ('00000000-0000-0000-0000-000000000201', 'patient.alex@example.test', 'Alex Rivera', 'patient', crypt(:'demo_password', gen_salt('bf', 12))),
    ('00000000-0000-0000-0000-000000000202', 'patient.bri@example.test', 'Bri Santos', 'patient', crypt(:'demo_password', gen_salt('bf', 12))),
    ('00000000-0000-0000-0000-000000000203', 'patient.casey@example.test', 'Casey Park', 'patient', crypt(:'demo_password', gen_salt('bf', 12))),
    ('00000000-0000-0000-0000-000000000204', 'patient.dev@example.test', 'Dev Patel', 'patient', crypt(:'demo_password', gen_salt('bf', 12))),
    ('00000000-0000-0000-0000-000000000205', 'patient.eli@example.test', 'Eli Brooks', 'patient', crypt(:'demo_password', gen_salt('bf', 12)))
ON CONFLICT (id) DO NOTHING;

INSERT INTO patients (user_id, clinician_id) VALUES
    ('00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-000000000101'),
    ('00000000-0000-0000-0000-000000000202', '00000000-0000-0000-0000-000000000101'),
    ('00000000-0000-0000-0000-000000000203', '00000000-0000-0000-0000-000000000101'),
    ('00000000-0000-0000-0000-000000000204', '00000000-0000-0000-0000-000000000102'),
    ('00000000-0000-0000-0000-000000000205', '00000000-0000-0000-0000-000000000102')
ON CONFLICT (user_id) DO NOTHING;
SQL
