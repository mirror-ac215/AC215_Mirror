# M5-09: Kubernetes/GKE repository handoff

These files are **repository preparation only**. They must be rendered with immutable Artifact Registry image coordinates and reviewed before any cluster action.

## Operator boundary

Owen prepares manifests and local tests only. Owen must not create, scale, deploy to, or validate a GKE cluster. Mostafa alone performs every paid-cloud action: creating the GKE cluster and GPU node pool, configuring Workload Identity and Secret Manager access, applying the rendered manifests, runtime/health validation, and stopped-state confirmation after paid use.

## Required operator-supplied inputs

- `MIRROR_IMAGE_REGISTRY`, `MIRROR_IMAGE_REPOSITORY`, `MIRROR_IMAGE_TAG` (a 40-character accepted-main SHA)
- `MIRROR_DOMAIN` in a public DNS zone that Mostafa can point to the GKE Ingress address during the operator-owned TLS handoff
- `MIRROR_CV_GSA` (the non-secret Google service-account email bound by Mostafa to the Kubernetes service account)
- `MIRROR_CV_MODEL_BUCKET`, `MIRROR_CV_MODEL_OBJECT`, and `MIRROR_CV_MODEL_VERSION` (non-secret coordinates of the Mostafa-approved serving artifact)
- a GKE cluster with a dedicated `nvidia-tesla-t4` node pool for `llm-service`
- a `mirror-runtime` Kubernetes Secret populated through the approved Secret Manager and Workload Identity process, never committed to this repository. It must contain these keys, with operator-supplied values only: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `MIRROR_DEMO_PASSWORD`, `DATABASE_URL`, `JWT_SIGNING_KEY`, and `TRUSTED_PROXY_IPS`. `TRUSTED_PROXY_IPS` must be a JSON array that includes `127.0.0.1/32`, because the in-pod Caddy sidecar is the gateway's immediate peer; otherwise all client-address attribution collapses to an untrusted proxy address.

## Render-only handoff

The raw manifests intentionally contain only non-secret placeholders. Kustomize does not expand shell `${...}` syntax itself, so render the files using the checked-in helper after exporting the required non-secret values:

```bash
cd infra/k8s
chmod +x render.sh
./render.sh
```

The helper validates the immutable SHA-tag format, replaces only the documented non-secret values in a temporary directory, and runs `kustomize build` to write `mirror-gke-rendered.yaml`. It does **not** call `kubectl`, `gcloud`, Secret Manager, or a cloud API. Inspect that generated bundle before Mostafa performs any separately approved cluster operation.

The gateway remains deliberately at one replica because session history and frame windows are currently in process memory. Its in-pod Caddy proxy mirrors the current `/api` stripping behavior and returns 404 for `/api/metrics` and any descendant path; do not scale it before session state is externalized or explicit affinity is accepted. The Caddy sidecar exposes a readiness endpoint at `/api/health`, so the GKE backend health check reaches the serving path rather than its default 404 root. The database is a single-replica StatefulSet with a PVC and initializes `PGDATA` below the mount root so a fresh disk's `lost+found` directory cannot block PostgreSQL initialization. CV and LLM startup probes allow up to ten minutes for dependency/model initialization.

## TLS handoff

The rendered bundle includes a GKE `ManagedCertificate` named `mirror-managed` and attaches it to the GCE Ingress. Mostafa alone applies the rendered manifest, verifies that the required public DNS record resolves to the Ingress address, waits for the managed certificate to become active, validates HTTPS routing, and records the non-sensitive result and stopped-state confirmation. This repository does not create a cluster, issue a certificate, change DNS, or perform TLS validation.

This initial foundation does not prove deployment, TLS issuance, GPU availability, Workload Identity binding, model access, or runtime health. Mostafa alone performs those paid-cloud steps and records stopped-state confirmation after paid use.
