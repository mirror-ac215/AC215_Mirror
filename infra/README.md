# infra

Local Docker Compose stack for Mirror (M2-03, v0).

## What runs

| Service | Built from | Port on your machine | Health check |
|---|---|---|---|
| `frontend` | `services/frontend` | 3000 | `GET /health` |
| `api-gateway` | `services/api-gateway` | 8000 | `GET /health` |
| `db` | `services/db` (Postgres 16 + schema + demo seed) | none (internal only) | `pg_isready` |

Start order is enforced with health checks: `db` must be healthy before `api-gateway` starts, and `api-gateway` must be healthy before `frontend` starts.

Inside the Compose network, services reach each other by service name. The gateway's default `DB_HOST=db` therefore finds the database with no extra configuration.

Not in the stack yet: `llm-service` (PR #16) and `cv-service` (M2-07). Until they are added, the gateway's `/health` reports `"status": "degraded"` with `cv-service` and `llm-service` as `down`. That is expected; the gateway still returns HTTP 200 and stays healthy.

## First run

From the repository root:

```bash
cp infra/.env.example infra/.env     # then fill in the two values
docker compose -f infra/compose.yml up --build -d
docker compose -f infra/compose.yml ps
```

All three services should show `(healthy)` after about a minute. Then:

- App: http://localhost:3000
- Gateway API docs: http://localhost:8000/docs

## Configuration (`infra/.env`)

Compose reads `infra/.env` automatically (it sits next to `compose.yml`). It is gitignored; never commit it.

| Variable | Used by | Purpose |
|---|---|---|
| `POSTGRES_PASSWORD` | `db` | Password for the `mirror_app` database user. Any local value works. |
| `MIRROR_DEMO_PASSWORD` | `db` and `api-gateway` | Password of the seeded demo users. The db seeds the users with it and the gateway checks logins against it, so both must get the same value. |

If either is missing, Compose refuses to start and names the missing variable.

Demo users (from `services/db/seed.sh`): `clinician.ada@example.test`, `patient.alex@example.test`, `patient.bri@example.test`, all with `MIRROR_DEMO_PASSWORD`.

## Everyday commands

```bash
docker compose -f infra/compose.yml logs -f api-gateway   # follow one service's logs
docker compose -f infra/compose.yml down                  # stop; keeps the database volume
docker compose -f infra/compose.yml down -v               # stop and wipe the database (re-seeds on next start)
```

The database lives in the named volume `db-data`. The schema and seed only run when that volume is empty, so use `down -v` after changing `init.sql` or `seed.sh`, or after changing `MIRROR_DEMO_PASSWORD`.

## Windows note

Shell scripts that run inside containers must keep LF line endings. The repository's `.gitattributes` enforces this. If a container exits with code 127 and `can't execute 'sh'`, the script was checked out with CRLF: delete it and run `git checkout -- <file>` to restore it with LF.
