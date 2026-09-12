#!/usr/bin/env bash
# Resets Postgres + reseeds + restarts the API only, leaving the web dev
# server alone. Brings the demo back to the same, fully populated Dee/Ada
# state rather than whatever the last session's real submissions left
# behind (state persists for real in Postgres).
set -euo pipefail

WEB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$(cd "$WEB_DIR/.." && pwd)"
RUN_DIR="$WEB_DIR/.demo"
mkdir -p "$RUN_DIR"

if [[ ! -f "$WEB_DIR/.env" ]]; then
  echo "!! demo-web/.env missing. Copy .env.example first: cp .env.example .env" >&2
  exit 1
fi
SERVICE_TOKEN="$(grep -m1 '^SERVICE_TOKEN=' "$WEB_DIR/.env" | cut -d= -f2-)"

# Ferry is the default demo data; set LEARNING_SEED=golden to reset onto
# the synthetic fixture instead.
LEARNING_SEED="${LEARNING_SEED:-ferry}"

OPENROUTER_API_KEY=""
if [[ -f "$API_DIR/.env" ]]; then
  OPENROUTER_API_KEY="$(grep -m1 '^OPENROUTER_API_KEY=' "$API_DIR/.env" | cut -d= -f2-)"
fi

# Kill by recorded pid, then anything still on :8000, never by process-name
# pattern (pkill -f) — that can catch an unrelated process on a shared box.
if [[ -f "$RUN_DIR/api.pid" ]]; then
  kill "$(cat "$RUN_DIR/api.pid")" 2>/dev/null || true
  rm -f "$RUN_DIR/api.pid"
fi
pids="$(lsof -ti :8000 2>/dev/null || true)"
[[ -n "$pids" ]] && kill $pids 2>/dev/null || true

echo "==> Resetting Postgres: agency-demo-pg"
docker rm -f agency-demo-pg >/dev/null 2>&1 || true
docker run -d --name agency-demo-pg \
  -e POSTGRES_DB=learning -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 postgres:16 >/dev/null
until docker exec agency-demo-pg pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done

export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/learning"
(cd "$API_DIR" && uv run alembic upgrade head)
(cd "$API_DIR" && uv run python -m learning_service.seed "$LEARNING_SEED")

(
  cd "$API_DIR"
  export DATABASE_URL
  export SERVICE_TOKEN="$SERVICE_TOKEN"
  export LEARNING_SEED="$LEARNING_SEED"
  export LEARNING_LLM=stub
  export OPENROUTER_MODEL="${OPENROUTER_MODEL:-openai/gpt-5.6-luna}"
  export OPENROUTER_API_KEY
  export PORT=8000
  uv run python -m learning_service.serve
) > "$RUN_DIR/api.log" 2>&1 &
echo $! > "$RUN_DIR/api.pid"

for _ in $(seq 1 60); do
  if curl -s http://localhost:8000/health 2>/dev/null | grep -q "\"seed\":\"$LEARNING_SEED\""; then
    echo "==> API ready (fresh $LEARNING_SEED seed)"
    exit 0
  fi
  sleep 1
done
echo "!! API did not become ready in time" >&2
exit 1
