# M5-09: Kubernetes/GKE repository handoff

These files are **repository preparation only**. They must be rendered with immutable Artifact Registry image coordinates and reviewed before any cluster action.

## Operator boundary

Owen prepares manifests and local tests only. Owen must not create, scale, deploy to, or validate a GKE cluster. Mostafa alone performs every paid-cloud action: creating the GKE cluster and GPU node pool, configuring Workload Identity and Secret Manager access, applying the rendered manifests, runtime/health validation, and stopped-state confirmation after paid use.

## Required operator-supplied inputs

- `MIRROR_IMAGE_REGISTRY`, `MIRROR_IMAGE_REPOSITORY`, `MIRROR_IMAGE_TAG` (a 40-character accepted-main SHA)
- `MIRROR_DOMAIN` and a managed TLS strategy
- a GKE cluster with a dedicated `nvidia-tesla-t4` node pool for `llm-service`
- a `mirror-runtime` Kubernetes Secret populated through the approved Secret Manager and Workload Identity process, never committed to this repository

Do not apply the raw files directly. Render only after providing the non-secret inputs, inspect the result, and let Mostafa run the approved GKE command. This initial foundation does not prove deployment, TLS issuance, GPU availability, or runtime health.
