# End-to-end smoke test

M4-05 verifies the accepted patient-to-clinician workflow against the real local Compose stack:

1. A seeded patient signs in.
2. The patient gives camera consent and starts a session with Chromium's synthetic camera stream.
3. The patient sends a non-crisis chat message and receives the mock LLM reply.
4. A seeded clinician signs in and sees the patient list assigned by the database.

The test never reads a physical camera, sends patient frames, downloads model artifacts, or performs cloud work.

## Local run

From the repository root, start a fresh local stack using an explicitly disposable Compose project, then run the test with the same non-secret local demo password:

```bash
export MIRROR_DEMO_PASSWORD=local-only-e2e-password
docker compose -p mirror-e2e -f infra/compose.yml up --build --wait
(cd tests/e2e && npm ci && npx playwright install --with-deps chromium && npm test)
docker compose -p mirror-e2e -f infra/compose.yml down -v
```

CI starts and removes its own Compose stack. `MIRROR_DEMO_PASSWORD` is only the local seeded-account password, not a cloud or production credential.
