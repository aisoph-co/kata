#!/usr/bin/env bash
# Runs the Playwright suite 5 consecutive times; fails on the first red run
# (decisions-2026-09-09-overnight.md row 12).
#
# Resets the demo database before each run (reset-demo-db.sh): learner
# state now persists for real in Postgres, so 5 runs of real submissions
# against the same database would gradually exhaust Dee's queue (everything
# mastered, nothing due) rather than testing the same fresh-morning state
# each time. Set SKIP_DB_RESET=1 to run against whatever is already up.
set -euo pipefail

RUNS="${RUNS:-5}"
cd "$(dirname "${BASH_SOURCE[0]}")/.."

for i in $(seq 1 "$RUNS"); do
  if [[ "${SKIP_DB_RESET:-}" != "1" ]]; then
    bash scripts/reset-demo-db.sh
  fi
  echo "==> e2e run $i/$RUNS"
  npm run e2e
done

echo "==> $RUNS/$RUNS green"
