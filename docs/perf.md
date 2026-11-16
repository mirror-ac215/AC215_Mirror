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

**Run 1: Nov 14, 2026. Camera pipeline without the emotion model (grey frame).**
Code under test: commit `2f18bb1` (later commits on this branch change only documentation), on
`main` `5a41478`. Julie's MacBook Air, local compose with cv-service (`cv-vit-b16-v4`) and the
mock LLM. 5 patients for 3 minutes per run: 93 replies and 568 frames with the camera on, 69
replies with the camera off. The raw stats files of this run were not kept; Run 2 publishes
its stats files (see below).

| Where | Measure | Result | Target | Verdict |
|---|---|---|---|---|
| local compose (mock LLM) | p95 full reply | 250 ms | < 5000 ms | mock only, not a verdict |
| local compose (mock LLM) | p95 first token, camera on - off (no emotion model) | 90 ms | - | transport and drop-path evidence only |
| local compose (mock LLM) | p95 frame upload | 110 ms | - | - |
| local compose (mock LLM) | failed requests (both runs) | 0 | 0 | meets target |

What this shows: the grey frame has no face, therefore cv-service ran the face detector and
returned before the emotion model (`services/cv-service/app/main.py`, lines 112-116), and the
gate answered "dropped". The 90 ms is the cost of frame uploads, face detection and the drop
path while 5 patients chat. It is **not** the camera's real overhead and does not show that the
300 ms target is met. The 250 ms reply time is the mock and says nothing about the real model.

**Run 2: to run. Camera overhead with a consented face frame (`ok` path).**
Same commands with `MIRROR_LOAD_FRAME` pointing at a consented face photo kept outside Git.
To record: the full commit SHA, the stats files under `tests/load/results/<run>/`, and the
"replies with a first-token time" row (must read "all"). This run decides the 300 ms target.

**Run 3: to run (MS5). The same test against the GPU VM** for the real reply time. Mostafa runs
the VM and will run it the next time the VM is up; MS4 does not require it.

## Read with care

- **Local compose uses the mock LLM.** Local reply times say nothing about the real model; only
  the camera overhead carries over.
- **One request at a time on the VM.** `MAX_NUM_SEQS=1` (`infra/compose.prod.yml`): with 5
  patients, replies queue. The VM run will show whether p95 still stays under 5 s.
- **Grey test frame.** By default no face is found, the emotion model never runs, the gate
  answers "dropped" and fusion runs text-only. Only a consented face frame (`MIRROR_LOAD_FRAME`)
  measures the camera's real overhead.
- **5 users, 3 minutes.** Enough for a p95 over roughly 100 replies, not a soak test. With under
  100 replies per run, the p95 rests on the slowest 4 or 5 replies; treat differences of a few
  tens of ms as noise.
