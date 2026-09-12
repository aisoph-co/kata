"""Package-data fixtures read at runtime via `importlib.resources` (spec
§Testing: a fixture other packages need does not require a network call or
a path outside the installed wheel to reach it).

`fixtures/ferry/` serves two issues (`fixtures/ferry/SOURCE.md`): CI1's
(KATA-13) grounding source for `GET /admin/ingest` (the seeded Ferry
payments team's `1-context/` material), and KATA-4's demo-seed scenario —
`load_ferry_scenario` below, the realistic payments-team roster, curriculum
and 60-day review history `learning_service.seed` writes to Postgres for
`LEARNING_SEED=ferry`.

    from learning_service.fixtures import load_ferry_scenario
    scenario = load_ferry_scenario()
"""

from __future__ import annotations

from typing import Any

__all__ = ["load_ferry_scenario"]


def load_ferry_scenario() -> dict[str, Any]:
    from learning_service.fixtures.ferry_scenario import build_ferry_scenario

    return build_ferry_scenario()
