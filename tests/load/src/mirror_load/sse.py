"""Time one streamed chat reply from the gateway's SSE events.

The gateway answers POST /sessions/{id}/messages with Server-Sent Events:
`token` events, then `done`; or a single `crisis` event (docs/contracts/api-gateway.openapi.yaml).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ReplyTiming:
    first_token_ms: float | None  # None when no token arrived (crisis, or an empty reply)
    complete_ms: float  # until `done`, `crisis`, or the end of the stream
    outcome: str  # "done", "empty" (`done` with no token), "crisis" or "incomplete"
    tokens: int


def time_reply(
    lines: Iterable[str],
    started: float,
    clock: Callable[[], float] = time.perf_counter,
) -> ReplyTiming:
    """Read SSE lines until the reply ends; times are milliseconds since `started`."""
    first_token_ms: float | None = None
    tokens = 0
    for line in lines:
        if not line.startswith("event:"):
            continue
        event = line.removeprefix("event:").strip()
        if event == "token":
            tokens += 1
            if first_token_ms is None:
                first_token_ms = (clock() - started) * 1000
        elif event in ("done", "crisis"):
            # A `done` with no token is a reply the patient never saw: report it as "empty",
            # therefore it counts as a failure and never drops out of the first-token numbers.
            outcome = "empty" if event == "done" and tokens == 0 else event
            return ReplyTiming(first_token_ms, (clock() - started) * 1000, outcome, tokens)
    return ReplyTiming(first_token_ms, (clock() - started) * 1000, "incomplete", tokens)
