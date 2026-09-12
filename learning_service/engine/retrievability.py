"""FSRS retrievability (spec §Learning engine, "FSRS"; `py-fsrs` uses the
same power-law forgetting curve). `due_at` drives "overdue"; retrievability
drives the order overdue cards are shown in — lowest (most forgotten)
first (spec §Learning engine, "Next-item selection", step 1).
"""

from __future__ import annotations

from datetime import datetime

# FSRS's power forgetting curve constants (FSRS-4.5 onward, incl. FSRS-6):
# R(t) = (1 + FACTOR * t / S) ** DECAY, calibrated so R(S) == 0.9.
_DECAY = -0.5
_FACTOR = 0.9 ** (1 / _DECAY) - 1


def retrievability(stability: float, last_review_at: datetime | None, now: datetime) -> float:
    if last_review_at is None or stability <= 0:
        return 0.0
    elapsed_days = max((now - last_review_at).total_seconds() / 86400, 0.0)
    return (1 + _FACTOR * elapsed_days / stability) ** _DECAY
