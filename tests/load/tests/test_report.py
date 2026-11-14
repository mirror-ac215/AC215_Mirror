import csv

import pytest
from mirror_load.report import (
    FIRST_TOKEN,
    FRAME,
    FULL_REPLY,
    read_stats,
    summarise,
    to_markdown,
)

HEADER = ["Type", "Name", "Request Count", "Failure Count", "50%", "95%"]


def write_stats(path, rows):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for name, count, failures, p50, p95 in rows:
            w.writerow(["SSE", name, count, failures, p50, p95])
        w.writerow(["", "Aggregated", 0, 0, 0, 0])
    return path


def test_meets_both_targets(tmp_path):
    on = read_stats(
        write_stats(
            tmp_path / "on.csv",
            [
                (FIRST_TOKEN, 40, 0, 300, 900),
                (FULL_REPLY, 40, 0, 1200, 3000),
                (FRAME, 400, 0, 50, 120),
            ],
        )
    )
    off = read_stats(
        write_stats(
            tmp_path / "off.csv", [(FIRST_TOKEN, 40, 0, 250, 700), (FULL_REPLY, 40, 0, 1100, 2800)]
        )
    )
    s = summarise(on, off)
    assert s.overhead_ms == 200 and s.overhead_ok
    assert s.reply_p95_ms == 3000 and s.reply_ok
    assert s.frame_p95_ms == 120
    assert "Aggregated" not in on


def test_misses_targets_and_counts_failures(tmp_path):
    on = read_stats(
        write_stats(
            tmp_path / "on.csv", [(FIRST_TOKEN, 10, 1, 900, 1500), (FULL_REPLY, 10, 2, 4000, 6000)]
        )
    )
    off = read_stats(
        write_stats(
            tmp_path / "off.csv", [(FIRST_TOKEN, 10, 0, 300, 800), (FULL_REPLY, 10, 0, 3000, 4000)]
        )
    )
    s = summarise(on, off)
    assert not s.reply_ok and not s.overhead_ok
    assert s.failures == 3
    table = to_markdown(s, "VM")
    assert "6000 ms" in table and "misses target" in table and "no frames sent" in table


def test_run_without_replies_is_an_error(tmp_path):
    empty = read_stats(write_stats(tmp_path / "e.csv", [(FRAME, 5, 5, 0, 0)]))
    with pytest.raises(ValueError, match="did any reply finish"):
        summarise(empty, empty)
