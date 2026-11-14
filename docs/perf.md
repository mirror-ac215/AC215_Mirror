# Performance (M4-07)

Load test: 5 patients chatting at once, camera on, against the api-gateway. Method, commands and
settings: [`tests/load/README.md`](../tests/load/README.md).

## Targets

| Measure | Target | Why |
|---|---|---|
| p95 time to a full reply | < 5 s | a patient waits for each reply |
| Camera overhead: p95 first token, camera on minus camera off | <= 300 ms | the camera should not slow the chat |

## Results

Rows come from `python -m mirror_load.report` after each run.

**Run 1: Nov 14, 2026, branch `jl/M4-07-load-test` on `main` 5a41478, Julie's MacBook Air,
local compose with cv-service (`cv-vit-b16-v4`) and the mock LLM, grey test frame.**
5 patients for 3 minutes per run: 93 replies and 568 frames with the camera on, 69 replies with
the camera off.

| Where | Measure | Result | Target | Verdict |
|---|---|---|---|---|
| local compose (mock LLM) | p95 full reply | 250 ms | < 5000 ms | meets target |
| local compose (mock LLM) | camera overhead (p95 first token, on - off) | 90 ms | <= 300 ms | meets target |
| local compose (mock LLM) | p95 frame upload | 110 ms | - | - |
| local compose (mock LLM) | failed requests (both runs) | 0 | 0 | meets target |

What this shows: with 5 patients sending a frame every 1.5 s, the camera adds about 90 ms to the
time before the first word of a reply (p95 first token 230 ms with the camera on, 140 ms off),
well inside the 300 ms target. The 250 ms reply time is the mock and says nothing about the real
model.

**Still to run:** the same test against the GPU VM for the real reply time (Mostafa runs the VM).

## Read with care

- **Local compose uses the mock LLM.** Local reply times say nothing about the real model; only
  the camera overhead carries over.
- **One request at a time on the VM.** `MAX_NUM_SEQS=1` (`infra/compose.prod.yml`): with 5
  patients, replies queue. The VM run will show whether p95 still stays under 5 s.
- **Grey test frame.** By default no face is found, the gate answers "dropped" and fusion runs
  text-only. A frame with a face exercises the "ok" path (`MIRROR_LOAD_FRAME`).
- **5 users, 3 minutes.** Enough for a p95 over roughly 100 replies, not a soak test. With under
  100 replies per run, the p95 rests on the slowest 4 or 5 replies; treat differences of a few
  tens of ms as noise.
