# infra

Local Docker Compose stack for Mirror (M2-03, v0).

## What runs

| Service | Built from | Port on your machine | Health check |
|---|---|---|---|
| `frontend` | `services/frontend` | 3000 | `GET /health` |
| `api-gateway` | `services/api-gateway` | 8000 | `GET /health` |
| `db` | `services/db` (Postgres 16 + schema + demo seed) | none (internal only) | `pg_isready` |
| `cv-service` (`cv` profile only) | `services/cv-service` | 8001 | `GET /health` after the configured CPU model loads |
| `llm-service` | `services/llm-service` (mock mode: no GPU, no model download) | none (internal only) | `GET /health` |

Start order is enforced with health checks: `db` and `llm-service` must be healthy before `api-gateway` starts, and `api-gateway` must be healthy before `frontend` starts.

Inside the Compose network, services reach each other by service name. The gateway's default `DB_HOST=db` therefore finds the database with no extra configuration.

`llm-service` runs in **mock mode** (the image's default build target): it answers the OpenAI-compatible chat API with deterministic replies, so the stack and its CI smoke test need no GPU and no model download. The real GPU target is documented in [`services/llm-service/README.md`](../services/llm-service/README.md).

`cv-service` is available behind the explicit `cv` Compose profile (`--profile cv`), because its real startup needs an approved GCS credential to download the model. The default stack and its CI smoke test do not enable that profile, so neither needs cloud credentials. Without the profile, the gateway's `/health` reports `"status": "degraded"` with only `cv-service` as `down`. That is expected; the gateway still returns HTTP 200 and stays healthy.

In production (`compose.prod.yml`) `cv-service` always runs, with no credential
file: it downloads the model at startup using the VM's configured attached
identity. Before pulling images, `deploy-stage-b.sh` obtains a token directly
from the VM metadata server and reads the configured
`CV_MODEL_BUCKET`/`CV_MODEL_OBJECT` metadata with that token. This fails
clearly unless `M3_13_SERVICE_ACCOUNT_EMAIL` has `roles/storage.objectViewer`
on the reviewed model bucket; a local gcloud user login cannot satisfy this
check. The helper then waits up to 600 seconds for
Compose health, so a model that cannot be loaded also fails the deployment.

To run CV locally, first export the path to an ADC credential file that is outside this repository, then explicitly enable the profile:

```bash
export CV_GOOGLE_APPLICATION_CREDENTIALS="$GOOGLE_APPLICATION_CREDENTIALS"
docker compose -f infra/compose.yml --profile cv up --build cv-service
```

The profile mounts that credential read-only and never copies it into an image. See [`services/cv-service/README.md`](../services/cv-service/README.md) for the model artifact and validation boundary.

## First run

From the repository root:

```bash
cp infra/.env.example infra/.env     # then fill in the four values
docker compose -f infra/compose.yml up --build -d
docker compose -f infra/compose.yml ps
```

All four default services (`db`, `llm-service`, `api-gateway`, and `frontend`)
should show `(healthy)` after about a minute. Then:

- App: http://localhost:3000
- Gateway API docs: http://localhost:8000/docs

## Configuration (`infra/.env`)

Compose reads `infra/.env` automatically (it sits next to `compose.yml`). It is gitignored; never commit it.

| Variable | Used by | Purpose |
|---|---|---|
| `DB_NAME` | `db`, `api-gateway` | PostgreSQL database name. The default development identity is `mirror`. |
| `DB_USER` | `db`, `api-gateway` | PostgreSQL application user. The default development identity is `mirror_app`. |
| `DB_PASSWORD` | `db`, `api-gateway` | Password for the configured database user. Any local value works. Compose derives the gateway's `DATABASE_URL` from this same value. |
| `MIRROR_DEMO_PASSWORD` | `db` | Password used only to seed local demo accounts. The M3 gateway's fixed demo-token compatibility layer does not read it; M4-02 replaces that layer with database-backed login. |

If any required value is missing, Compose refuses to start and names the missing variable.

### Migration from the pre-M3-10 `infra/.env`

Existing local files used `POSTGRES_PASSWORD` and `MIRROR_DEMO_PASSWORD`. Before starting this
revision, replace the former with the explicit database settings, preserving its value:

```dotenv
DB_NAME=mirror
DB_USER=mirror_app
DB_PASSWORD=<the previous POSTGRES_PASSWORD value>
MIRROR_DEMO_PASSWORD=<existing value>
```

Remove `POSTGRES_PASSWORD`; Compose no longer reads it. **Do not reset `db-data` merely for this
environment-variable migration** when those database identity values are unchanged. A reset is
required only when changing `init.sql`, `seed.sh`, or `MIRROR_DEMO_PASSWORD`, as described below.

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

For GCP provisioning and VM bootstrap, use Cloud Shell or a Linux/macOS shell. Git Bash on Windows can pass CRLF-terminated `gcloud` output into the provisioning shell script and is not supported for those commands.

## M3-13 Stage A: GPU VM deployment foundation

> **Scope boundary:** Stage A prepares and proves the secure GPU deployment
> platform. It does **not** mean that the fully integrated MS3 user journey is
> deployed. M3-14 adds SHA-tagged Artifact Registry images; Stage B deploys the
> complete locally validated integration once the relevant M3-03 through M3-12
> work has merged.

Stage A uses one GCP VM with a T4 GPU. Docker Compose keeps the application
containers on a private network. Caddy is the only public entry point: it
terminates HTTPS, routes `/` to the Node frontend, and strips `/api` before
routing to the FastAPI gateway. The database, model server, gateway, frontend
container ports and CV service are not individually exposed to the Internet.

### 1. Provision the VM

The provisioning script is intentionally fail-closed: it creates missing resources,
but it only reuses an existing resource after its security-relevant configuration
matches the requested configuration. It creates a dedicated custom VPC and
subnetwork rather than using GCP's default VPC, so default-network SSH rules
cannot expose the VM. It requires explicit inputs so it cannot accidentally
deploy into an unknown project or zone.

Before running it, a project administrator must approve billing, a T4-capable
zone, GPU quota, a narrow VM service account, and the team CIDRs allowed to
reach the VM. The configured `M3_13_SERVICE_ACCOUNT_EMAIL` needs only the
eventual artifact-read permissions: Artifact Registry Reader for immutable
images and `roles/storage.objectViewer` on the reviewed CV-model bucket. Do
not give the VM Owner or Editor.

```bash
export M3_13_PROJECT_ID='your-project-id'
export M3_13_ZONE='us-central1-a'             # confirm this zone has T4 quota
export M3_13_SERVICE_ACCOUNT_EMAIL='mirror-vm@your-project-id.iam.gserviceaccount.com'
# Comma-separated, approved public source CIDRs, for example your team's fixed egress IPs.
# Only narrow canonical ranges are accepted: IPv4 /24 or narrower, IPv6 /64 or narrower.
export M3_13_PUBLIC_SOURCE_RANGES='203.0.113.10/32,198.51.100.20/32'
bash infra/gcp/provision-t4-vm.sh
```

The script enables Compute Engine, reserves/reuses a static IP, permits HTTP
and HTTPS only from the explicitly approved source ranges, permits SSH only
through IAP's documented source range, and creates/reuses a labelled T4 VM.
It rejects Internet-wide public ingress while the gateway still uses demo
authentication. Review the planned project and values before executing it:
provisioning a VM and reserving an IP can incur cost.

Make `CADDY_DOMAIN` resolve to the printed static IP for approved clients,
using a team DNS zone or controlled local-host mapping. Because TCP 80/443 is
restricted to approved CIDRs while M4-02 authentication is pending, Stage A
uses Caddy's private CA rather than public ACME. This is an encrypted,
team-only deployment, not a public service.

### 2. Bootstrap Docker and NVIDIA support

Mostafa, as the paid-cloud operator, connects through IAP and runs the bootstrap script. It requests Ubuntu's
supported NVIDIA 535 driver series, Docker Engine, the Compose plugin and NVIDIA
Container Toolkit, then configures Docker's NVIDIA runtime. On a fresh VM the
script exits after installing the kernel driver with a reboot instruction;
reboot, reconnect through IAP, and rerun it. It calls `nvidia-smi` and the
Docker GPU test only after a successful post-reboot run.

The Ubuntu `nvidia-driver-535` package can resolve to a newer compatible runtime
(the working VM reported 580). Treat the `nvidia-smi` output recorded after the
bootstrap as the authoritative installed driver version. The script also adds the
invoking non-root deploy operator to the Docker group whether it was invoked via
`sudo` or as an ordinary user; log out and back in before using Docker without sudo.

```bash
gcloud compute ssh mirror-gpu-prod \
  --project "$M3_13_PROJECT_ID" \
  --zone "$M3_13_ZONE" \
  --tunnel-through-iap \
  --command 'bash -s' < infra/gcp/bootstrap-vm.sh
```

Expected proof:

```text
nvidia-smi                                  # host detects the T4
docker run --rm --gpus all ... nvidia-smi   # Docker can use the T4
docker compose version
```

### 3. Prepare host-only configuration and model material

On the VM, clone the reviewed branch/revision. Copy the example to a local
file, restrict it to its owner, and fill it using values that never enter Git:

```bash
cp infra/.env.prod.example infra/.env.prod
chmod 600 infra/.env.prod
```

Production serves the plain base model with no adapter (D-006), so nothing
needs downloading here. Prefer the VM service account for GCS access; do not
place a service-account key, model adapter, Hugging Face token, or database
password in the repository, an image layer, logs, or pull request.

### 4. Start and validate Stage A

After the team-access hostname resolves, run the manual deployment helper from
the checked-out reviewed revision:

```bash
bash infra/deploy-stage-a.sh
```

It validates the combined Compose configuration, starts the stack with health
checks, and prints the Git revision to record. Caddy stores its private CA in
the persisted `caddy-data` volume.

On the VM, export the root certificate after the stack is healthy:

```bash
docker compose --env-file infra/.env.prod -f infra/compose.yml -f infra/compose.prod.yml \
  exec -T caddy cat /data/caddy/pki/authorities/local/root.crt > "$HOME/mirror-stage-a-root.crt"
chmod 600 "$HOME/mirror-stage-a-root.crt"
```

From the approved client, copy the root certificate through IAP, then import it
into that client's trust store for browser access or use it directly with
`curl --cacert`:

```bash
gcloud compute scp mirror-gpu-prod:~/mirror-stage-a-root.crt "$HOME/mirror-stage-a-root.crt" \
  --project "$M3_13_PROJECT_ID" --zone "$M3_13_ZONE" --tunnel-through-iap
curl -fsSI --cacert "$HOME/mirror-stage-a-root.crt" "http://$CADDY_DOMAIN"          # expect HTTPS redirect
curl -fsS --cacert "$HOME/mirror-stage-a-root.crt" "https://$CADDY_DOMAIN/health"   # frontend health
curl -fsS --cacert "$HOME/mirror-stage-a-root.crt" "https://$CADDY_DOMAIN/api/health" # gateway via Caddy
```

Also record `nvidia-smi`, the Docker GPU test, the real LLM `/health` result,
one safe non-streaming completion, and one completed streaming completion.
Do not send sensitive or patient-like content for this smoke test.

### Recovery and cost control

- Inspect: `docker compose --env-file infra/.env.prod -f infra/compose.yml -f infra/compose.prod.yml ps`
- Logs: append `logs --tail=200 <service>` to the same command.
- Stop containers while retaining volumes: append `down`.
- Stop the VM when not demonstrating: `gcloud compute instances stop mirror-gpu-prod --zone "$M3_13_ZONE" --project "$M3_13_PROJECT_ID"`.
- Delete the VM and release the reserved address only after the team approves
  teardown; both affect availability and, for the address, billing.

## M3-14: immutable Artifact Registry images

M3-14 separates image publication from VM deployment. The main-only workflow
`.github/workflows/publish-artifact-registry-images.yml` builds Mirror's `db`,
`api-gateway`, `cv-service`, `frontend`, and real-target `llm-service` images,
then publishes each using the exact merged Git SHA as its tag. It uses GitHub
OIDC, not a committed service-account key.

Before enabling the workflow, a project administrator must configure these
**repository variables** (not secrets) in GitHub:

| Variable | Meaning |
|---|---|
| `GCP_PROJECT_ID` | GCP project containing the registry. |
| `GAR_LOCATION` | Artifact Registry location, for example `us-central1`. |
| `GAR_REPOSITORY` | Image path after the registry host, normally `<project-id>/<repository>`. |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Full GitHub Actions Workload Identity Provider resource name. |
| `GCP_SERVICE_ACCOUNT` | CI service-account email with only Artifact Registry Writer for this repository. |

Until all variables are configured, the workflow records a clear skip notice and
does not attempt authentication or image publication, so ordinary `main` merges
remain green. Configure Workload Identity Federation to permit only this
repository's `main` branch and keep the VM service account limited to Artifact
Registry Reader. Never use
`GOOGLE_CREDENTIALS`, a service-account key JSON, or a long-lived token in the
repository, workflow, or VM configuration.

### Artifact Registry retention policy

The real GPU image is multi-gigabyte, and every accepted revision has an
immutable SHA tag. Before enabling publication, a project administrator must
apply [`artifact-registry-cleanup-policy.json`](artifact-registry-cleanup-policy.json).
It retains the ten most recent versions of each `mirror-` image package and
deletes `mirror-` versions older than 30 days. It does not apply to unrelated
packages that share the repository. The CI identity remains Artifact Registry
Writer only; applying or changing a repository cleanup policy is a separate
administrator action.

First apply it in dry-run mode and inspect the resulting Artifact Registry audit
logs. Enable Artifact Registry Data Access `DATA_WRITE` audit logging before the
dry run, otherwise the cleanup-policy results will not be available there.
Cleanup evaluation runs asynchronously and can take about a day:

```bash
gcloud artifacts repositories set-cleanup-policies "$GAR_REPOSITORY" \
  --project="$GCP_PROJECT_ID" \
  --location="$GAR_LOCATION" \
  --policy=infra/artifact-registry-cleanup-policy.json \
  --dry-run
```

After confirming that the active VM image and any rollback image are retained,
apply the same policy for real:

```bash
gcloud artifacts repositories set-cleanup-policies "$GAR_REPOSITORY" \
  --project="$GCP_PROJECT_ID" \
  --location="$GAR_LOCATION" \
  --policy=infra/artifact-registry-cleanup-policy.json \
  --no-dry-run
```

After the publication run for an accepted `main` SHA succeeds, set these
non-secret values in VM-only `infra/.env.prod`:

```bash
MIRROR_IMAGE_REGISTRY='<location>-docker.pkg.dev'
MIRROR_IMAGE_REPOSITORY='<project-id>/<repository>'
MIRROR_IMAGE_TAG='<40-character merged Git SHA>'
```

Check out that exact SHA on the VM and deploy with:

```bash
bash infra/deploy-stage-b.sh
```

Before its first pull, the helper uses the VM's attached identity to configure
Docker credential helper access for `MIRROR_IMAGE_REGISTRY` (for example
`us-central1-docker.pkg.dev`). It then rejects a non-SHA tag or a mismatch
between the checkout and `MIRROR_IMAGE_TAG`, resolves the three Compose files,
pulls immutable images, and starts without local builds.

Before starting vLLM, `infra/prepare-llm-model.sh` reuses the public-model snapshot in the same default Hugging Face hub cache that vLLM serves from, with `HF_HUB_DISABLE_XET=1`. It parses `config.json`, hashes every safetensors shard against the SHA-256 in its Hugging Face LFS blob filename, and re-downloads only a mismatched shard before rechecking it. This detects truncated or structurally corrupt cached shards before `/health` can incorrectly report ready. It does not retrieve the LoRA adapter, write credentials, or prove semantic model quality. `LLM_FORCE_MODEL_DOWNLOAD` defaults to `0`; set it to `1` only for an intentional full refresh. The real LLM container allows a 600-second health start period, disables the T4-incompatible FlashInfer sampler by default, and the deploy helper requires the fixed smoke reply to contain `READY` and prints that non-patient response. This is an operational smoke check, not a substitute for the reviewed LLM evaluation suite.

Record `docker compose ... images` output with the resolved image digests as the
M3-14 VM-pull evidence. Do not start, stop, or redeploy the VM from this project
role: notify Owen when this reviewed helper is ready, and Mostafa performs the
paid-cloud operation and confirms the VM is stopped afterwards.
