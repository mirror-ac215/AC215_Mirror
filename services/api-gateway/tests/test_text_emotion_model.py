"""Real-model check for M3-05: < 100 ms per message on CPU.

Skipped by default (it downloads the ~330 MB model). Run it on your laptop:

    RUN_MODEL_TESTS=1 uv run pytest tests/test_text_emotion_model.py -q -s
"""

import os
import statistics

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MODEL_TESTS") != "1",
    reason="set RUN_MODEL_TESTS=1 to download and run the real model",
)

MESSAGES = [
    "I had a really rough day at work and I just feel drained.",
    "Honestly I'm excited, I finally got the job!",
    "I keep worrying that something bad is going to happen.",
    "Whatever. It doesn't matter anyway.",
    "That's disgusting, I can't believe they did that.",
    "Wait, what? I did not see that coming.",
    "I'm so angry at myself for messing this up again.",
    "Not much to report, just a normal week.",
] * 5  # 40 messages


def test_real_model_labels_and_cpu_latency() -> None:
    from app.text_emotion import LABELS, TextEmotion

    module = TextEmotion()
    module.warm_up()  # first call loads the model; don't count it

    latencies = []
    for message in MESSAGES:
        result = module.analyse(message)
        assert result.top2[0][0] in LABELS
        latencies.append(result.latency_ms)

    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(0.95 * len(latencies)) - 1]
    print(f"\ntext-emotion on CPU: p50 {p50:.1f} ms, p95 {p95:.1f} ms, n={len(latencies)}")
    assert p95 < 100, f"p95 {p95:.1f} ms is over the 100 ms target"

    # Sanity check on clear-cut messages.
    assert module.analyse("I finally got the job, I'm so happy!").top2[0][0] == "joy"
    assert module.analyse("I'm terrified of what the doctor will say.").top2[0][0] == "fear"
