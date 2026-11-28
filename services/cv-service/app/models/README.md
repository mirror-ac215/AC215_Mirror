# Model files (not committed)

Model weights are never committed to Git. This folder is filled at build or test time.

| File | What | Source | Licence | sha256 |
|---|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | YuNet face detector (232,589 bytes), used by `app/runtime.py` and the fairness audit (M4-26, PR #118) | [opencv_zoo](https://github.com/opencv/opencv_zoo/tree/f12e12798e8314f7c074a6656816c048dcc95b7a/models/face_detection_yunet), commit `f12e127` | MIT | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |

`app/fetch_models.py` downloads it from that pinned commit and refuses a file with a different sha256. The Docker build runs it, the tests run it when the file is missing, and you can run it by hand from `services/cv-service`:

```bash
uv run python -m app.fetch_models
```

The expression model (ViT-B/16 v4) is not stored here either: cv-service downloads it from Cloud Storage at start-up.
