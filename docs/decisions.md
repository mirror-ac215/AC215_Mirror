# Mirror decision log

This log records cross-component decisions that affect more than one owner or
that must be preserved when an implementation pull request is later merged.
It does not turn an unmerged pull request into merged functionality.

## Status values

- **Accepted** — the team has agreed the decision and implementation can rely on it.
- **Proposed** — awaiting the affected owners' review; do not treat it as a
  merged implementation fact.
- **Superseded** — kept for history, but replaced by a later decision.

## D-001: Keep local DVC reproduction separate from shared GCS publication

- **Status:** Accepted and implemented in M2-06 (PR #24).
- **Decision:** `dvc repro` validates and materializes the declared local
  processed-data output only. Uploading to the versioned GCS artifact prefix is
  a separate explicit `--publish` action.
- **Why:** A normal reproducibility check should not require cloud credentials
  or silently change shared storage. Explicit publication makes shared state
  intentional and auditable.
- **Affected areas:** `dvc.yaml`, preprocessing README, artifact inventory,
  and future training/evaluation consumers.

## D-002: Use Node/Nitro SSR for the frontend runtime

- **Status:** Proposed pending M2-12 Part A review and merge.
- **Decision:** The frontend target is a Node/Nitro server-side-rendering
  runtime on port 3000, with an unauthenticated `GET /health` endpoint, rather
  than an nginx-only static runtime.
- **Why:** TanStack Start requires a server runtime for SSR and its route-based
  health endpoint. Caddy/Compose integration must route to this documented
  runtime after M2-03 is implemented.
- **Affected areas:** frontend Dockerfile/README, architecture, Compose, Caddy,
  and deployment documentation.

## How to add a decision

Add a new numbered entry whenever a decision changes a shared contract,
runtime, data/artifact boundary, deployment behavior, or another component
owner's implementation. State its status, the decision, its reason, and the
affected repository areas. Link the approving issue or pull request when one
exists.
