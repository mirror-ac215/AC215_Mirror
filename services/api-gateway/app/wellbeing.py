"""Long-session wellbeing (M4-16).

Sessions have no time limit. After a long stretch Mirror suggests a break once, and after a
longer one the clinician gets a non-urgent review flag: a very long session can mean distress
or over-reliance. Both thresholds are placeholders in config until the team agrees real times.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

BREAK_MESSAGE = (
    "We've been talking for a while now. It might be a good moment to take a short break, "
    "stretch or get some water. I'll be here whenever you want to continue."
)


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class SessionClock:
    """Per-session state: when the session started and what was already done."""

    started_at: datetime
    break_after_min: float
    flag_after_min: float
    now: Callable[[], datetime] = field(default=utc_now)
    break_suggested: bool = False
    flagged: bool = False

    def minutes(self) -> float:
        return (self.now() - self.started_at).total_seconds() / 60

    def break_due(self) -> bool:
        return not self.break_suggested and self.minutes() >= self.break_after_min

    def flag_due(self) -> bool:
        return not self.flagged and self.minutes() >= self.flag_after_min


def break_payload() -> dict:
    return {"kind": "break_suggestion", "message": BREAK_MESSAGE}
