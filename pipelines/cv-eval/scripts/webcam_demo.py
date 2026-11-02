"""Live webcam demo: what v3 and v4 read from your face, frame by frame and smoothed.

Uses the same face finder and preprocessing as cv-service (largest Haar face, grey -> 3 channels,
224x224, ImageNet normalisation), so what you see here is what Mirror would see. Nothing is saved.

Run from the repository root (needs the CUDA torch in cv-eval's venv and opencv-python):
    uv run --no-sync --project pipelines/cv-eval python pipelines/cv-eval/scripts/webcam_demo.py

Keys: q quit | m switch v4 / v3 / both | p tight face box / box with 15 % margin
"""

from __future__ import annotations

import argparse
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms

from mirror_cv_eval.cli import load_model

LABELS = ("angry", "disgust", "fear", "happy", "neutral", "sad", "surprise")
TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
])
# The M3-04 gate defaults (services/api-gateway/app/config.py).
MIN_FRAMES, MIN_FACE_RATIO, MIN_TOP, MIN_MARGIN, MIN_STABILITY = 3, 0.5, 0.40, 0.10, 0.60


def find_face(frame_bgr: np.ndarray, cascade: cv2.CascadeClassifier, margin: float):
    grey = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(grey, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: int(f[2]) * int(f[3]))
    dx, dy = round(w * margin), round(h * margin)
    x0, y0 = max(0, x - dx), max(0, y - dy)
    x1, y1 = min(frame_bgr.shape[1], x + w + dx), min(frame_bgr.shape[0], y + h + dy)
    return (x0, y0, x1, y1)


def gate(window: deque, now: float, seconds: float) -> tuple[str, list[tuple[str, float]], float]:
    """Simplified M3-04: average the last `seconds` of readings, check confidence and stability."""
    recent = [r for r in window if now - r[0] <= seconds]
    faces = [r[1] for r in recent if r[1] is not None]
    if len(faces) < MIN_FRAMES or len(faces) / max(len(recent), 1) < MIN_FACE_RATIO:
        return "dropped", [], 0.0
    mean = np.mean(faces, axis=0)
    order = np.argsort(mean)[::-1]
    top, second = order[0], order[1]
    stability = float(np.mean([np.argmax(p) == top for p in faces]))
    ok = mean[top] >= MIN_TOP and mean[top] - mean[second] >= MIN_MARGIN and stability >= MIN_STABILITY
    return ("ok" if ok else "uncertain"), [(LABELS[top], mean[top]), (LABELS[second], mean[second])], stability


def draw_bars(panel: np.ndarray, x: int, title: str, probs: np.ndarray | None, verdict: tuple) -> None:
    cv2.putText(panel, title, (x, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    for i, label in enumerate(LABELS):
        y = 60 + i * 30
        value = 0.0 if probs is None else float(probs[i])
        cv2.putText(panel, f"{label:8s}", (x, y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.rectangle(panel, (x + 90, y), (x + 90 + int(180 * value), y + 18), (90, 180, 120), -1)
        cv2.putText(panel, f"{value:.2f}", (x + 280, y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    status, top2, stability = verdict
    colour = {"ok": (90, 200, 90), "uncertain": (60, 180, 230), "dropped": (120, 120, 120)}[status]
    cv2.putText(panel, f"10 s gate: {status}", (x, 290), cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)
    if top2:
        text = f"{top2[0][0]} {top2[0][1]:.2f} / {top2[1][0]} {top2[1][1]:.2f}  stab {stability:.2f}"
        cv2.putText(panel, text, (x, 318), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1)


def main() -> int:
    command = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    command.add_argument("--v4", type=Path, default=Path("data/models/m3-01-C3.pth"))
    command.add_argument("--v3", type=Path,
                         default=Path("../../CSCI E-25 - Computer Vision/CV Project/vit_b16_v3_best.pth"))
    command.add_argument("--camera", type=int, default=0)
    command.add_argument("--window", type=float, default=10.0, help="seconds averaged by the gate")
    args = command.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    models = {"v4": load_model(args.v4).to(device), "v3": load_model(args.v3).to(device)}
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    windows = {name: deque(maxlen=600) for name in models}
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        raise SystemExit(f"could not open camera {args.camera}")
    show, margin = "both", 0.0
    print(__doc__.split("Keys:")[1].strip(), f"| running on {device}")

    while True:
        ok, frame = camera.read()
        if not ok:
            break
        now = time.monotonic()
        box = find_face(frame, cascade, margin)
        probs: dict[str, np.ndarray | None] = {name: None for name in models}
        crop_view = np.zeros((112, 112, 3), dtype=np.uint8)
        if box is not None:
            x0, y0, x1, y1 = box
            face = Image.fromarray(cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)).convert("L").convert("RGB")
            batch = TRANSFORM(face).unsqueeze(0).to(device)
            with torch.inference_mode():
                for name, model in models.items():
                    probs[name] = torch.softmax(model(batch).float(), dim=1)[0].cpu().numpy()
            crop_view = cv2.cvtColor(np.asarray(face.resize((112, 112))), cv2.COLOR_RGB2BGR)
            cv2.rectangle(frame, (x0, y0), (x1, y1), (90, 200, 90), 2)
        for name in models:
            windows[name].append((now, probs[name]))

        frame = cv2.resize(frame, (640, int(frame.shape[0] * 640 / frame.shape[1])))
        frame[8:120, 8:120] = crop_view  # what the model sees (grey, as in cv-service)
        shown = ["v4", "v3"] if show == "both" else [show]
        panel = np.full((frame.shape[0], 340 * len(shown), 3), 30, dtype=np.uint8)
        for i, name in enumerate(shown):
            draw_bars(panel, 10 + 340 * i, f"{name} (now)", probs[name], gate(windows[name], now, args.window))
        footer = f"crop: {'tight' if margin == 0 else '+15% margin'}   keys: q quit, m model, p crop"
        cv2.putText(panel, footer, (10, panel.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1)
        cv2.imshow("Mirror CV demo (nothing is saved)", np.hstack([frame, panel]))

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("m"):
            show = {"both": "v4", "v4": "v3", "v3": "both"}[show]
        if key == ord("p"):
            margin = 0.15 if margin == 0 else 0.0
    camera.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
