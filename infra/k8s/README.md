# M5-09: Kubernetes/GKE repository handoff

These files are **repository preparation only**. They must be rendered with immutable Artifact Registry image coordinates and reviewed before any cluster action.

## Operator boundary

Owen prepares manifests and local tests only. Owen must not create, scale, deploy to, or validate a GKE cluster. Mostafa alone performs every paid-cloud action: creating the GKE cluster and GPU node pool, configuring Workload Identity and Secret Manager access, applying the rendered manifests, runtime/health validation, and stopped-state confirmation after paid use.

## Required operator-supplied inputs

- `MIRROR_IMAGE_REGISTRY`, `MIRROR_IMAGE_REPOSITORY`, `MIRROR_IMAGE_TAG` (a 40-character accepted-main SHA)
- `MIRROR_DOMAIN` and a managed TLS strategy
- `MIRROR_CV_GSA` (the non-secret Google service-account email bound by Mostafa to the Kubernetes service account)
- `MIRROR_CV_MODEL_BUCKET`, `MIRROR_CV_MODEL_OBJECT`, and `MIRROR_CV_MODEL_VERSION` (non-secret coordinates of the Mostafa-approved serving artifact)
- a GKE cluster with a dedicated `nvidia-tesla-t4` node pool for `llm-service`
- a `mirror-runtime` Kubernetes Secret populated through the approved Secret Manager and Workload Identity process, never committed to this repository

## Render-only handoff

The raw manifests intentionally contain only non-secret placeholders. Kustomize does not expand shell `${...}` syntax itself, so render the files using the checked-in helper after exporting the required non-secret values:

```bash
cd infra/k8s
chmod +x render.sh
./render.sh
```

The helper validates the immutable SHA-tag format, replaces only the documented non-secret values in a temporary directory, and runs `kustomize build` to write `mirror-gke-rendered.yaml`. It does **not** call `kubectl`, `gcloud`, Secret Manager, or a cloud API. Inspect that generated bundle before Mostafa performs any separately approved cluster operation.

The gateway remains deliberately at one replica because session history and frame windows are currently in process memory. Its in-pod Caddy proxy mirrors the current `/api` stripping behavior and returns 404 for `/api/metrics`; do not scale it before session state is externalized or explicit affinity is accepted. The database is a single-replica StatefulSet with a PVC. CV and LLM startup probes allow up to ten minutes for dependency/model initialization.

This initial foundation does not prove deployment, TLS issuance, GPU availability, Workload Identity binding, model access, or runtime health. Mostafa alone performs those paid-cloud steps and records stopped-state confirmation after paid use.
