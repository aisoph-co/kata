#!/usr/bin/env bash
# One command for the morning (PLAN_06 §Stack): Postgres, migrate, seed
# ferry (default; `LEARNING_SEED=golden` for the synthetic fixture), API on
# :8000, web on :5173. `--real-llm` skips LEARNING_LLM=stub.
#
# web/ lives inside the agency-v1 repo itself — the API is one level up
# (`..`), on whichever branch/checkout this is. Needs migration 0005 +
# the ferry seed and its `uv` environment installed (`cd .. && uv sync`).
set -euo pipefail

REAL_LLM=false
[[ "${1:-}" == "--real-llm" ]] && REAL_LLM=true

# Ferry (Kata's real payments-course cast) is the default demo data; set
# LEARNING_SEED=golden to fall back to the synthetic fixture.
LEARNING_SEED="${LEARNING_SEED:-ferry}"

WEB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$(cd "$WEB_DIR/.." && pwd)"
RUN_DIR="$WEB_DIR/.demo"
mkdir -p "$RUN_DIR"

if [[ ! -d "$API_DIR" ]]; then
  echo "!! $API_DIR not found." >&2
  exit 1
fi
if [[ ! -f "$API_DIR/migrations/versions/0005_learning_state.py" ]]; then
  echo "!! $API_DIR is on $(git -C "$API_DIR" branch --show-current) — need the branch with migration 0005 (review/card_state/concept_state)." >&2
  exit 1
fi
if [[ ! -f "$WEB_DIR/.env" ]]; then
  echo "!! demo-web/.env missing. Copy .env.example first: cp .env.example .env" >&2
  exit 1
fi

# Idempotent: `npm run demo` twice in a row must not leak the first API/web
# processes. Kill by recorded pid, then anything still listening on our
# ports, then drop the (now-stale) pid files. Never kill by process-name
# pattern (pkill -f) — that can catch an unrelated process of someone
# else's on a shared box.
for f in api.pid web.pid; do
  if [[ -f "$RUN_DIR/$f" ]]; then
    kill "$(cat "$RUN_DIR/$f")" 2>/dev/null || true
    rm -f "$RUN_DIR/$f"
  fi
done
for port in 8000 5173; do
  pids="$(lsof -ti :"$port" 2>/dev/null || true)"
  [[ -n "$pids" ]] && kill $pids 2>/dev/null || true
done

# demo-web/.env carries SERVICE_TOKEN — the same value the API must require,
# since the Vite proxy injects it as the bearer token on every /api/* call.
SERVICE_TOKEN="$(grep -m1 '^SERVICE_TOKEN=' "$WEB_DIR/.env" | cut -d= -f2-)"

# OPENROUTER_API_KEY lives only in the API repo root .env — read it, never
# echo it.
OPENROUTER_API_KEY=""
if [[ -f "$API_DIR/.env" ]]; then
  OPENROUTER_API_KEY="$(grep -m1 '^OPENROUTER_API_KEY=' "$API_DIR/.env" | cut -d= -f2-)"
fi

echo "==> Postgres: agency-demo-pg (5432, db 'learning')"
docker rm -f agency-demo-pg >/dev/null 2>&1 || true
docker run -d --name agency-demo-pg \
  -e POSTGRES_DB=learning -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 postgres:16 >/dev/null
until docker exec agency-demo-pg pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done

export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/learning"

echo "==> Creating schema"
(cd "$API_DIR" && uv run python "$WEB_DIR/scripts/create-schema.py")

echo "==> Seeding $LEARNING_SEED scenario (idempotent)"
(cd "$API_DIR" && uv run python -m learning_service.seed "$LEARNING_SEED")

LEARNING_LLM_VALUE="stub"
$REAL_LLM && LEARNING_LLM_VALUE=""

echo "==> API on :8000 (llm=${LEARNING_LLM_VALUE:-openrouter})"
(
  cd "$API_DIR"
  export DATABASE_URL
  export SERVICE_TOKEN="$SERVICE_TOKEN"
  export LEARNING_SEED="$LEARNING_SEED"
  export OPENROUTER_MODEL="${OPENROUTER_MODEL:-openai/gpt-5.6-luna}"
  export OPENROUTER_API_KEY
  export PORT=8000
  if [[ -n "$LEARNING_LLM_VALUE" ]]; then export LEARNING_LLM="$LEARNING_LLM_VALUE"; else unset LEARNING_LLM || true; fi
  # exec: this subshell process *becomes* uv, not a parent of it — but uv
  # itself may still fork the real python listener as a child, so `$!`
  # below is only a launcher pid either way. Resolved to the real
  # listener via `lsof` once health responds (see below) — that's the
  # pid `demo-down.sh`/`kill $(cat api.pid)` actually needs.
  exec uv run python -m learning_service.serve
) > "$RUN_DIR/api.log" 2>&1 &
echo $! > "$RUN_DIR/api.pid"

echo "==> Web on :5173"
(cd "$WEB_DIR" && exec npm run dev) > "$RUN_DIR/web.log" 2>&1 &
echo $! > "$RUN_DIR/web.pid"

# Both launchers can fork a further child that's the real listener (uv,
# npm) — wait for each port to actually answer, then overwrite the pid
# file with whatever `lsof` reports is bound to it, so a plain
# `kill $(cat .demo/api.pid)` (or web.pid) stops the real process, not
# just the shell that launched it.
echo "==> Waiting for API/web to bind their ports"
for _ in $(seq 1 60); do
  curl -s http://localhost:8000/health >/dev/null 2>&1 && break
  sleep 1
done
api_listener="$(lsof -ti :8000 2>/dev/null | head -1 || true)"
[[ -n "$api_listener" ]] && echo "$api_listener" > "$RUN_DIR/api.pid"

for _ in $(seq 1 60); do
  curl -s -o /dev/null http://localhost:5173 2>/dev/null && break
  sleep 1
done
web_listener="$(lsof -ti :5173 2>/dev/null | head -1 || true)"
[[ -n "$web_listener" ]] && echo "$web_listener" > "$RUN_DIR/web.pid"

echo "==> Up. API log: $RUN_DIR/api.log · Web log: $RUN_DIR/web.log"
echo "    Open http://localhost:5173 — stop with 'npm run demo:down'."
