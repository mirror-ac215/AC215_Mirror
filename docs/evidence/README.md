# MS2 evidence: it runs, end to end

Recorded on **Oct 16, 2026** on a Windows 11 laptop from `main` plus this PR's changes (Docker Desktop, the full stack including the opt-in `cv` profile). Each file shows one claim from the MS2 deliverables.

| # | File | What it proves |
|---|---|---|
| 1 | `01_compose_ps.txt` · `01_docker_desktop.png` | **One command starts the whole system:** `docker compose -f infra/compose.yml --profile cv up --build -d` → 5 containers, all healthy (db, llm-service, cv-service, api-gateway, frontend) |
| 2 | `02_health.json` · `02_cv_health.json` | The gateway sees every dependency (`cv-service`, `llm-service`, `db`: ok); cv-service is healthy and reports model version `cv-vit-b16-v3`. The model source it is configured to download at start-up (`gs://mirror-ac215-data/models/cv/inherited-v3/vit_b16_v3_best.pth`) is documented in [services/cv-service/README.md](../../services/cv-service/README.md), and the download path is covered by `tests/test_model_runtime.py`. |
| 3 | `03_chat_sample.txt` · `03_app_chat.png` | **Sample input → output:** a patient message goes in and the reply streams back word by word (Server-Sent Events), ending with the context object. The screenshot shows the same flow in the web app, served by the frontend container and talking to the real gateway. |
| 3 | `03_cv_predict_sample.txt` | **Camera model input → output:** a 48×48 FER-2013 test face finds no face (`face_found: false`); the same face at webcam size is read correctly (*happy* 0.66, not uncertain). This is the "dataset photo vs live webcam" gap the MS3 retrain on video frames addresses. |
| 4 | `04_frame_guards.txt` | The gateway's rules hold in the running system: 202 valid frame · 401 no login · 403 another patient's session · 409 no camera consent · 415 not a JPEG · 413 over 1 MB |
| 5 | `05_dvc_reproducibility.txt` | **Data versioning:** on a fresh clone, `dvc status` is up to date. Rebuilding the persona data from raw gives the same output fingerprint (`md5: 62c01999…`), so `dvc.lock` is unchanged. |
| 6 | `06_cv_train_smoke.txt` | The new baseline training job (`pipelines/cv-train`) runs on the real DVC dataset, end to end: data → augmentation → focal loss → validation → test → checkpoint. This is a seeded CPU smoke test (1 epoch, 2 batches) that checks the code path, not model quality; a full re-run is expected to land near the 0.6445 baseline, not to match it exactly (see `pipelines/cv-train/README.md`). |
| 7 | `07_wandb_eval_run.png` | **Experiment tracking:** the baseline evaluation in W&B: macro-F1 0.6445 on 7,178 test images, per-class F1 identical to the original training notebook ([run](https://wandb.ai/mog941-harvard-university/mirror/runs/vqa4ulfz)) |
| 7 | `07_ci_green.png` | CI on a pull request: only the changed components are tested, and the required `CI summary` check passes |

**Not in this folder, on purpose:** no data, images, model weights, tokens or passwords. The demo login token stayed in a shell variable; FER-2013 images are not redistributed.

**Reproduce it yourself:** follow the [README](../../README.md) quick start (`.env` with two values, then `docker compose up`), then `dvc pull`. cv-service additionally needs `CV_GOOGLE_APPLICATION_CREDENTIALS` in `infra/.env` pointing at your Google application-default credentials, which are mounted read-only and never copied into the image (see [infra/README.md](../../infra/README.md)).
