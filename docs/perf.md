# Performance (M4-07)

Load test: 5 patients chatting at once, camera on, against the api-gateway. Method, commands and
settings: [`tests/load/README.md`](../tests/load/README.md).

## Targets

| Measure | Target | Why |
|---|---|---|
| p95 time to a full reply | < 5 s | a patient waits for each reply |
| Camera overhead: p95 first token, camera on minus camera off | <= 300 ms | the camera should not slow the chat |

## Results

**Not run yet.** Rows are added by `python -m mirror_load.report` after each run, with the
date, commit and where it ran.

| Where | Measure | Result | Target | Verdict |
|---|---|---|---|---|

## Read with care

- **Local compose uses the mock LLM.** Local reply times say nothing about the real model; only
  the camera overhead carries over.
- **One request at a time on the VM.** `MAX_NUM_SEQS=1` (`infra/compose.prod.yml`): with 5
  patients, replies queue. The VM run will show whether p95 still stays under 5 s.
- **Grey test frame.** By default no face is found, the gate answers "dropped" and fusion runs
  text-only. A frame with a face exercises the "ok" path (`MIRROR_LOAD_FRAME`).
- **5 users, 3 minutes.** Enough for a p95 over roughly 100 replies, not a soak test.
