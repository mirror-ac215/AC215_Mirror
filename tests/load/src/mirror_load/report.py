"""Turn two Locust runs (camera on, camera off) into the numbers for docs/perf.md.

Targets (task board, M4-07):
- p95 time to a full reply under 5 s;
- the camera's overhead at most 300 ms: p95 time to the first token with the camera on,
  minus the same with the camera off. On and off use the same 5 users, messages and pacing,
  therefore the difference is the work the camera adds to a turn (frames, gate, fusion).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

REPLY_TARGET_MS = 5000.0
CAMERA_OVERHEAD_TARGET_MS = 300.0

FIRST_TOKEN = "reply: first token"
FULL_REPLY = "reply: complete"
FRAME = "/sessions/{id}/frames"


@dataclass(frozen=True)
class Row:
    name: str
    count: int
    failures: int
    p50_ms: float
    p95_ms: float


def read_stats(path: Path) -> dict[str, Row]:
    """Rows of a Locust `<prefix>_stats.csv`, by request name ("Aggregated" excluded)."""
    rows: dict[str, Row] = {}
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            if r["Name"] == "Aggregated":
                continue
            rows[r["Name"]] = Row(
                name=r["Name"],
                count=int(r["Request Count"]),
                failures=int(r["Failure Count"]),
                p50_ms=float(r["50%"]),
                p95_ms=float(r["95%"]),
            )
    return rows


@dataclass(frozen=True)
class Summary:
    reply_p95_ms: float
    reply_ok: bool
    overhead_ms: float
    overhead_ok: bool
    frame_p95_ms: float | None
    failures: int


def summarise(camera_on: dict[str, Row], camera_off: dict[str, Row]) -> Summary:
    """The two target checks. The reply target is judged on the camera-on run (the slower one)."""
    for name in (FIRST_TOKEN, FULL_REPLY):
        if name not in camera_on or name not in camera_off:
            raise ValueError(f"missing '{name}' in a run: did any reply finish?")
    reply_p95 = camera_on[FULL_REPLY].p95_ms
    overhead = camera_on[FIRST_TOKEN].p95_ms - camera_off[FIRST_TOKEN].p95_ms
    frame = camera_on.get(FRAME)
    failures = sum(r.failures for r in camera_on.values()) + sum(
        r.failures for r in camera_off.values()
    )
    return Summary(
        reply_p95_ms=reply_p95,
        reply_ok=reply_p95 < REPLY_TARGET_MS,
        overhead_ms=overhead,
        overhead_ok=overhead <= CAMERA_OVERHEAD_TARGET_MS,
        frame_p95_ms=frame.p95_ms if frame else None,
        failures=failures,
    )


def to_markdown(s: Summary, where: str) -> str:
    """Rows for the results table in docs/perf.md."""

    def verdict(ok: bool) -> str:
        return "meets target" if ok else "misses target"

    frame = f"{s.frame_p95_ms:.0f} ms" if s.frame_p95_ms is not None else "no frames sent"
    rows = [
        (
            "p95 full reply",
            f"{s.reply_p95_ms:.0f} ms",
            "< 5000 ms",
            verdict(s.reply_ok),
        ),
        (
            "camera overhead (p95 first token, on - off)",
            f"{s.overhead_ms:.0f} ms",
            "<= 300 ms",
            verdict(s.overhead_ok),
        ),
        ("p95 frame upload", frame, "-", "-"),
        ("failed requests (both runs)", str(s.failures), "0", verdict(s.failures == 0)),
    ]
    return "\n".join(f"| {where} | {a} | {b} | {c} | {d} |" for a, b, c, d in rows)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Summarise a camera-on and a camera-off run.")
    parser.add_argument("camera_on", type=Path, help="<prefix>_stats.csv of the camera-on run")
    parser.add_argument("camera_off", type=Path, help="<prefix>_stats.csv of the camera-off run")
    parser.add_argument("--where", default="local compose (mock LLM)")
    args = parser.parse_args()
    print(
        to_markdown(summarise(read_stats(args.camera_on), read_stats(args.camera_off)), args.where)
    )


if __name__ == "__main__":
    main()
