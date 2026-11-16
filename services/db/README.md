# Mirror database service

PostgreSQL 16 container for Mirror's demo users, patient assignments, chat sessions, messages, aggregated emotion windows, and clinician review flags.

## What this service stores

- login-capable user records with a role and password hash;
- patient-to-clinician assignments;
- chat sessions and messages;
- aggregated emotion signals for the clinician dashboard;
- review flags created by the gateway safety flow.

## What this service never stores

- raw webcam frames;
- image blobs, image paths, or base64 image data;
- plaintext passwords.

## Files

| File | Purpose |
|---|---|
| `init.sql` | Executable schema: tables, foreign keys, constraints, and indexes. |
| `seed.sh` | Creates two clinicians, five demo patients, and patient assignments using the caller-provided local demo password. |
| `demo-history.sql` | Two weeks of demo sessions, emotion windows and review flags for Bri and Casey, so the clinician dashboard (M4-01) has data on a fresh stack. Alex stays empty (the dashboard's empty state, and the Compose chat test's own rows). Messages are placeholders. |
| `entrypoint-wrapper.sh` | Refuses an empty-volume initialization before PostgreSQL can create partial data unless the required local secrets are present. |
| `Dockerfile` | PostgreSQL 16 image with first-start initialization scripts and a health check. |
| `.env.example` | Safe local environment-variable names and sample values. |
| `tests/test_database.sh` | Builds and starts a real temporary container, then verifies schema, seeds, health, and constraints. |

## Run locally

```bash
cd services/db
cp .env.example .env
set -a; source .env; set +a

docker build --tag mirror-db .
docker run -d --name mirror-db \
  -e POSTGRES_DB \
  -e POSTGRES_USER \
  -e POSTGRES_PASSWORD \
  -e MIRROR_DEMO_PASSWORD \
  -v mirror-db-data:/var/lib/postgresql/data \
  -p 5432:5432 \
  mirror-db
```

Check health:

```bash
docker inspect --format '{{.State.Health.Status}}' mirror-db
```

Inspect the seed counts:

```bash
docker exec -it mirror-db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT role, count(*) FROM users GROUP BY role ORDER BY role;"

docker exec -it mirror-db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT count(*) AS demo_patients FROM patients;"
```

Stop the local container:

```bash
docker rm -f mirror-db
```

## Run the integration test

```bash
cd services/db
bash tests/test_database.sh
```

The test builds the image, starts a temporary container, waits for the Docker health check, and confirms:

- all six required tables exist;
- exactly two clinician users and five patient records are seeded;
- every seeded patient has a clinician assignment;
- raw-frame storage does not exist;
- invalid roles, invalid patient/clinician assignments, cross-patient review flags, unassigned clinician reviewers, patient reviewers, role changes that would break assignments, session ownership changes that would invalidate review flags, flagged-message moves across patients, and orphaned messages are rejected.
- an empty-volume startup without `MIRROR_DEMO_PASSWORD` fails before database initialization; retrying with the same volume and a supplied password seeds all seven users.

## First-start behavior and reset

The official PostgreSQL entrypoint runs `init.sql` and `seed.sh` only when its data directory is empty. This is intentional.

To rebuild local demo data after changing `init.sql` or `seed.sh`:

```bash
docker rm -f mirror-db 2>/dev/null || true
docker volume rm mirror-db-data
```

Then rerun the local startup commands above.

## Demo credentials

Before starting the database, set unique local-only values for both `POSTGRES_PASSWORD` and `MIRROR_DEMO_PASSWORD` in the copied `.env` file. The entrypoint wrapper refuses to initialize an empty volume when `MIRROR_DEMO_PASSWORD` is absent. `seed.sh` passes the local demo password only at initialization and converts it to bcrypt-style hashes through PostgreSQL's `pgcrypto` extension; no shared demo or database password is stored in the repository or image.

These identities are for local course demonstrations only. They are not production accounts and must never be exposed publicly.

## Compose handoff

M2-03 owns the shared `infra/compose.yml`. The database service needs:

```text
Service name: db
Internal port: 5432
Health command: pg_isready
Persistent volume: /var/lib/postgresql/data
Environment: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, MIRROR_DEMO_PASSWORD
Initialization: /docker-entrypoint-initdb.d/10-init.sql and 20-seed.sh
```
