"""Per-person derived metrics shared by `GET /me/progress`, `GET
/team/people/{id}`, and `GET /team/overview`: retention at 1/7/30 days,
bypass rate, and calibration — computed from the `review` log only, never
shipped raw to `/team/*` (spec §Privacy: concept-level only, never
per-review detail).

Retention bands (spec §Team analytics + row 3/`RetentionBand` in the
contract): of the reviews whose gap since the previous rep of the *same
item* falls in the band, the share graded correct (`rating >= 3`). Each
band reports both `accuracy` and its `samples` count; `accuracy` is `null`
under `_MIN_RETENTION_SAMPLES` rather than a misleadingly precise share
computed from a handful of reviews, but `samples` is always the real count.

`calibration` = mean stated confidence rescaled from 1-5 onto 0-1 as
`(c-1)/4`, minus accuracy, both computed only over reviews that carry a
`confidence`. Positive = over-confident, negative = under-confident.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from learning_service.engine.models import Review, as_utc

RETENTION_BANDS: dict[str, tuple[int, int]] = {"d1": (1, 1), "d7": (5, 10), "d30": (21, 45)}
_MIN_RETENTION_SAMPLES = 5


def _empty_retention() -> dict[str, dict[str, Any]]:
    return {band: {"accuracy": None, "samples": 0} for band in RETENTION_BANDS}


def _band_reviews(reviews: Sequence[Review], key: Callable[[Review], Any]) -> dict[str, list[Review]]:
    """Group `reviews` by `key`, then bucket the *later* review of each
    same-key consecutive pair into the retention band its gap falls in."""
    grouped: dict[Any, list[Review]] = defaultdict(list)
    for r in reviews:
        grouped[key(r)].append(r)

    band_reviews: dict[str, list[Review]] = {band: [] for band in RETENTION_BANDS}
    for group in grouped.values():
        group.sort(key=lambda r: as_utc(r.reviewed_at))
        for earlier, later in zip(group, group[1:]):
            gap_days = (as_utc(later.reviewed_at) - as_utc(earlier.reviewed_at)).days
            for band, (lo, hi) in RETENTION_BANDS.items():
                if lo <= gap_days <= hi:
                    band_reviews[band].append(later)
    return band_reviews


def _retention(band_reviews: dict[str, list[Review]]) -> dict[str, dict[str, Any]]:
    return {
        band: {
            "accuracy": (sum(1 for r in rs if r.rating >= 3) / len(rs) if len(rs) >= _MIN_RETENTION_SAMPLES else None),
            "samples": len(rs),
        }
        for band, rs in band_reviews.items()
    }


def person_learning_summary(reviews: Sequence[Review]) -> dict[str, Any]:
    """`reviews` is one person's own review log rows, any order."""
    if not reviews:
        return {
            "retention": _empty_retention(),
            "bypass_rate": None,
            "calibration": None,
            "review_count": 0,
            "last_active": None,
        }

    ordered = sorted(reviews, key=lambda r: as_utc(r.reviewed_at))
    review_count = len(ordered)
    last_active: datetime = as_utc(ordered[-1].reviewed_at)

    bypass_rate = sum(1 for r in ordered if r.bypassed) / review_count

    confidence_reviews = [r for r in ordered if r.confidence is not None]
    if confidence_reviews:
        mean_confidence = sum(r.confidence for r in confidence_reviews) / len(confidence_reviews)
        confidence_accuracy = sum(1 for r in confidence_reviews if r.rating >= 3) / len(confidence_reviews)
        # (c - 1) / 4, not c / 5: confidence is a 1-5 Likert, so the lowest
        # statement a learner can make must map to 0.0.
        calibration = (mean_confidence - 1) / 4 - confidence_accuracy
    else:
        calibration = None

    retention = _retention(_band_reviews(ordered, key=lambda r: r.item_id))

    return {
        "retention": retention,
        "bypass_rate": bypass_rate,
        "calibration": calibration,
        "review_count": review_count,
        "last_active": last_active,
    }


def subtree_retention(reviews: Sequence[Review]) -> dict[str, dict[str, Any]]:
    """Team-aggregate retention: the same bands, pooled across every person
    in `reviews` — grouped by `(person_id, item_id)` so a rep of the same
    item by two different people is never mistaken for one learner's
    repeat. Concept-level/aggregate only: no per-item or per-person detail
    leaves this function."""
    if not reviews:
        return _empty_retention()
    return _retention(_band_reviews(reviews, key=lambda r: (r.person_id, r.item_id)))
