"""Per-person derived metrics shared by `GET /me/progress`, `GET
/team/people/{id}`, and `GET /team/overview` (Contract v1.2.0, web-app-design.md
Contract change #2): retention at 1/7/30 days, bypass rate, and calibration.

All three are computed from the `review` log only — never shipped raw to
`/team/*` (spec §Privacy: concept-level only, never per-review detail).

Retention bands and formula: `docs/seed/README.md` / `OPEN-QUESTIONS.md` Q2's
working definition, adopted as-is by web-app-design.md Contract change #3 — of
the reviews whose gap since the previous rep of the *same item* falls in the
band, the share graded correct (`rating >= 3`). Each band reports both
`accuracy` and its `samples` count; `accuracy` is `null` under
`_MIN_RETENTION_SAMPLES` rather than a misleadingly precise share computed
from a handful of reviews, but `samples` is always the real count — QA
finding A, 2026-09-10: a thin individual band (e.g. Hugo's d30, 1 sample)
should still be visible as "not enough data" rather than indistinguishable
from zero, and the team-aggregate band (`subtree_retention`, pooled by
`(person_id, item_id)` so two different people's reps of the same item are
never treated as one learner's repeat) usually clears the floor even when an
individual doesn't.

`calibration` = mean stated confidence scaled to 0-1, minus accuracy, both
computed over only the reviews that carry a `confidence` — a stricter
denominator than upstream `verify_demo_beats.py`'s `calib()`, which divides by
*all* of a person's reviews regardless of whether they stated one. Identical
on Ferry (every one of its 2,199 reviews carries a confidence), so this
diverges only for a person with some confidence-less reviews (tech-lead
review, 2026-09-10). Positive means over-confident, negative under-confident.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

RETENTION_BANDS: dict[str, tuple[int, int]] = {"d1": (1, 1), "d7": (5, 10), "d30": (21, 45)}
_MIN_RETENTION_SAMPLES = 5


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _parse(reviewed_at: Any) -> datetime:
    if isinstance(reviewed_at, datetime):
        return _as_utc(reviewed_at)
    return datetime.fromisoformat(str(reviewed_at).replace("Z", "+00:00"))


def _empty_retention() -> dict[str, dict[str, Any]]:
    return {band: {"accuracy": None, "samples": 0} for band in RETENTION_BANDS}


def _band_reviews(
    reviews: list[dict[str, Any]], key: Callable[[dict[str, Any]], Any]
) -> dict[str, list[dict[str, Any]]]:
    """Group `reviews` by `key` (an item, or a (person, item) pair for a
    pooled multi-person set), then bucket the *later* review of each
    same-key consecutive pair into the retention band its gap falls in."""
    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for r in reviews:
        grouped[key(r)].append(r)

    band_reviews: dict[str, list[dict[str, Any]]] = {band: [] for band in RETENTION_BANDS}
    for group in grouped.values():
        group.sort(key=lambda r: _parse(r["reviewed_at"]))
        for earlier, later in zip(group, group[1:]):
            gap_days = (_parse(later["reviewed_at"]) - _parse(earlier["reviewed_at"])).days
            for band, (lo, hi) in RETENTION_BANDS.items():
                if lo <= gap_days <= hi:
                    band_reviews[band].append(later)
    return band_reviews


def _retention(band_reviews: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    return {
        band: {
            "accuracy": (
                sum(1 for r in rs if r["rating"] >= 3) / len(rs) if len(rs) >= _MIN_RETENTION_SAMPLES else None
            ),
            "samples": len(rs),
        }
        for band, rs in band_reviews.items()
    }


def person_learning_summary(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """`reviews` is one person's own review log rows (`repo.reviews_for`),
    any order. Returns `{retention: {d1: {accuracy, samples}, d7: ..., d30:
    ...}, bypass_rate, calibration, review_count, last_active}`.
    """
    if not reviews:
        return {
            "retention": _empty_retention(),
            "bypass_rate": None,
            "calibration": None,
            "review_count": 0,
            "last_active": None,
        }

    ordered = sorted(reviews, key=lambda r: _parse(r["reviewed_at"]))
    review_count = len(ordered)
    last_active = _parse(ordered[-1]["reviewed_at"])

    bypass_rate = sum(1 for r in ordered if r.get("bypassed")) / review_count

    confidence_reviews = [r for r in ordered if r.get("confidence") is not None]
    if confidence_reviews:
        mean_confidence = sum(r["confidence"] for r in confidence_reviews) / len(confidence_reviews)
        confidence_accuracy = sum(1 for r in confidence_reviews if r["rating"] >= 3) / len(confidence_reviews)
        # (c - 1) / 4, not c / 5: confidence is a 1-5 Likert, so the lowest
        # statement a learner can make must map to 0.0. Dividing by 5 floors
        # the scale at 0.2 and reports someone who always states confidence 1
        # and is always wrong as +0.2 "overconfident" when they are in fact
        # perfectly calibrated.
        calibration = (mean_confidence - 1) / 4 - confidence_accuracy
    else:
        calibration = None

    retention = _retention(_band_reviews(ordered, key=lambda r: r["item_id"]))

    return {
        "retention": retention,
        "bypass_rate": bypass_rate,
        "calibration": calibration,
        "review_count": review_count,
        "last_active": last_active,
    }


def subtree_retention(reviews: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Team-aggregate retention (QA finding A, 2026-09-10): the same bands,
    pooled across every person in `reviews` (each row must carry its own
    `person_id`) — grouped by `(person_id, item_id)` so a rep of the same
    item by two different people is never mistaken for one learner's
    repeat. Concept-level/aggregate only: no per-item or per-person detail
    leaves this function.
    """
    if not reviews:
        return _empty_retention()
    return _retention(_band_reviews(reviews, key=lambda r: (r["person_id"], r["item_id"])))
