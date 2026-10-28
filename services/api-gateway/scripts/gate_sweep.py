"""Choose the gate's thresholds on real video (M3-04 threshold sweep, step 2).

Replays per-frame probabilities (pipelines/cv-eval/scripts/export_frame_probs.py) through the real
gate() the way Mirror sees a webcam: one frame per second, and a 10-second window ending at every
second of every video. For each threshold combination it measures
- coverage:  share of windows the gate calls "ok" (how often Mirror gets a face signal at all)
- precision: share of those "ok" windows whose top emotion is the window's true emotion
and picks the combination with the most coverage that still reaches the target precision.

Run from services/api-gateway (W&B logging is optional):
    uv run --with wandb python -m scripts.gate_sweep ../../data/reports/v4_affwild2_val_frames.csv \\
        --wandb-project mirror
"""

from __future__ import annotations

import argparse
import csv
import itertools
from collections import Counter, defaultdict
from pathlib import Path

from app.config import Settings
from app.gating import FrameReading, gate

LABELS = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]
GRID = {
    "gate_min_top_prob": [0.30, 0.35, 0.40, 0.45, 0.50],
    "gate_min_margin": [0.05, 0.10, 0.15, 0.20],
    "gate_min_stability": [0.50, 0.60, 0.70, 0.80],
}


def load_videos(path: Path, fps: float) -> dict[str, list[tuple[FrameReading, str]]]:
    """Per video, one (reading, true label) per 1/fps seconds, like a webcam sending frames."""
    frames: dict[str, list[dict]] = defaultdict(list)
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            frames[row["video"]].append(row)
    videos = {}
    for video, rows in frames.items():
        rows.sort(key=lambda row: float(row["t"]))
        sampled, next_t = [], float("-inf")
        for row in rows:
            t = float(row["t"])
            if t >= next_t:
                probs = {label: float(row[label]) for label in LABELS}
                sampled.append((FrameReading(ts=t, face_found=True, probs=probs), row["label"]))
                next_t = t + 1.0 / fps
        videos[video] = sampled
    return videos


def windows(videos: dict, window_s: float) -> list[tuple[list[FrameReading], str]]:
    """A window ending at every sampled frame; its truth is the most common label inside it."""
    result = []
    for sampled in videos.values():
        for end, (last, _) in enumerate(sampled):
            inside = [(r, label) for r, label in sampled[: end + 1] if last.ts - r.ts < window_s]
            truth = Counter(label for _, label in inside).most_common(1)[0][0]
            result.append(([r for r, _ in inside], truth))
    return result


def score(cases: list, settings: Settings) -> dict[str, float]:
    statuses = Counter()
    hits, per_class = 0, defaultdict(lambda: [0, 0])  # true class -> [ok windows, correct]
    for readings, truth in cases:
        visual = gate(readings, settings, camera_on=True)
        statuses[visual["status"]] += 1
        if visual["status"] == "ok":
            correct = visual["top2"][0][0] == truth
            hits += correct
            per_class[truth][0] += 1
            per_class[truth][1] += correct
    ok = statuses["ok"]
    return {
        "coverage": ok / len(cases),
        "precision": hits / ok if ok else 0.0,
        "dropped": statuses["dropped"] / len(cases),
        "classes_seen_ok": sum(1 for n, _ in per_class.values() if n),
        **{f"precision_{label}": per_class[label][1] / per_class[label][0] if per_class[label][0] else 0.0
           for label in LABELS},
    }


def main() -> int:
    command = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    command.add_argument("frames", type=Path, help="CSV from export_frame_probs.py")
    command.add_argument("--fps", type=float, default=1.0, help="frames per second the frontend sends")
    command.add_argument("--target", type=float, default=0.70, help="precision the gate must reach")
    command.add_argument("--wandb-project", help="log every combination to this W&B project")
    args = command.parse_args()

    base = Settings()
    cases = windows(load_videos(args.frames, args.fps), base.gate_window_s)
    results = []
    for values in itertools.product(*GRID.values()):
        thresholds = dict(zip(GRID, values, strict=True))
        results.append({**thresholds, **score(cases, Settings(**thresholds))})

    current = next(r for r in results if all(r[k] == getattr(base, k) for k in GRID))
    reaching = [r for r in results if r["precision"] >= args.target]
    best = max(reaching, key=lambda r: r["coverage"]) if reaching else max(results, key=lambda r: r["precision"])
    print(f"{len(cases)} windows from {args.frames.name} at {args.fps} fps, target precision {args.target:.0%}")
    for name, r in (("current", current), ("chosen", best)):
        print(f"{name:8s} top>={r['gate_min_top_prob']:.2f} margin>={r['gate_min_margin']:.2f} "
              f"stability>={r['gate_min_stability']:.2f} -> ok in {r['coverage']:.0%} of windows, "
              f"right {r['precision']:.0%} of the time")

    # The trade-off curve: settings where no other choice is both more often ok and more often right.
    print("best trade-offs (coverage -> precision):")
    frontier = []
    for r in sorted(results, key=lambda r: -r["coverage"]):
        if not frontier or r["precision"] > frontier[-1]["precision"]:
            frontier.append(r)
    for r in frontier:
        print(f"  ok {r['coverage']:4.0%} -> right {r['precision']:.0%}   (top>={r['gate_min_top_prob']:.2f}, "
              f"margin>={r['gate_min_margin']:.2f}, stability>={r['gate_min_stability']:.2f})")

    if args.wandb_project:
        import wandb

        run = wandb.init(project=args.wandb_project, job_type="gate-sweep",
                         config={"frames": args.frames.name, "fps": args.fps, "target": args.target,
                                 "window_s": base.gate_window_s, "n_windows": len(cases)})
        columns = list(results[0])
        run.log({"sweep": wandb.Table(columns=columns, data=[[r[c] for c in columns] for r in results])})
        run.summary.update({f"chosen/{k}": v for k, v in best.items()} | {f"current/{k}": v for k, v in current.items()})
        run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
