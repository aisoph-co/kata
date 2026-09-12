#!/usr/bin/env bash
# Stops what demo-up.sh started: web, API, and the Postgres container.
set -euo pipefail

WEB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$WEB_DIR/.demo"

# `pkill -P $pid` only reaches direct children — `npm run dev`/`uv run`
# nest the actual listening process (vite, uvicorn) a level or two deeper,
# so it survived and kept 5173/8000 bound. Kill by recorded pid, then
# anything still on the ports, never by process-name pattern (pkill -f
# matched an unrelated process on a shared box before).
for name in web api; do
  pid_file="$RUN_DIR/$name.pid"
  if [[ -f "$pid_file" ]]; then
    kill "$(cat "$pid_file")" 2>/dev/null || true
    rm -f "$pid_file"
  fi
done
for port in 8000 5173; do
  pids="$(lsof -ti :"$port" 2>/dev/null || true)"
  [[ -n "$pids" ]] && kill $pids 2>/dev/null || true
done

echo "==> Stopping agency-demo-pg"
docker rm -f agency-demo-pg >/dev/null 2>&1 || true

echo "==> Down."
