# Bundled model files

| File | What | Source | Licence | sha256 |
|---|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | YuNet face detector (232,589 bytes), used by `app/runtime.py` and the fairness audit (M4-26) | [opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | MIT | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |

The expression model (ViT-B/16 v4) is not stored here: cv-service downloads it from Cloud Storage at start-up.
