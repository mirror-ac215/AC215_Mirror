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
Code under test: commit `2f18bb1`. Later commits on this branch add the Run 2 measurement, SSE accounting, retained aggregate evidence, and documentation; they do not retroactively make Run 1 a model-path measurement. It ran on
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
300 ms target is met; Run 2 measures that. The 250 ms reply time is the mock and says nothing
about the real model.

**Run 2: Nov 20, 2026. Camera overhead with a consented face frame (`ok` path).**
Code under test: commit `2b9dd0f2e1a26736ecaf5058fe5afa21af8464e4`, clean working tree. Julie's
MacBook Air, local compose with cv-service (`cv-vit-b16-v4`) and the mock LLM. Frame:
`MIRROR_LOAD_FRAME` set to a consented face photo of a team member, kept outside Git. 5 patients for
3 minutes per run: 95 replies with the camera on, 91 with the camera off. Stats files:
[`tests/load/results/2026-11-20-local-face/`](../tests/load/results/2026-11-20-local-face/).

| Where | Measure | Result | Target | Verdict |
|---|---|---|---|---|
| local compose (mock LLM) | p95 full reply | 290 ms | < 5000 ms | mock only, not a verdict |
| local compose (mock LLM) | camera overhead (p95 first token, camera on - off) | 90 ms | <= 300 ms | meets target |
| local compose (mock LLM) | p95 frame upload | 290 ms | - | - |
| local compose (mock LLM) | failed requests (both runs) | 0 | 0 | meets target |
| local compose (mock LLM) | replies with a first-token time (both runs) | 186 of 186 | all | complete |

What this shows: the photo took the `ok` path. The gateway's gate counter
(`mirror_gateway_gate_total`, read from `/metrics` after both runs on a freshly started stack)
reads `ok` 90, `dropped` 5, `camera_off` 91: 90 of the 95 camera-on turns used the emotion model,
and the 91 camera-off turns match the camera-off run. The p95 frame upload rose from 110 ms
(Run 1, grey frame) to 290 ms, the cost of the emotion model on each frame. With the model
running, the camera adds 90 ms to the p95 first token: the 300 ms target is met locally. The
reply time is the mock and says nothing about the real model (Run 3).

To check the rows: `cd tests/load && uv run python -m mirror_load.report
results/2026-11-20-local-face/camera-on_stats.csv results/2026-11-20-local-face/camera-off_stats.csv`.

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
