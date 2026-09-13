#!/bin/sh
# KATA-14 (demo round): starts W10's CopilotKit runtime (Node, listens on
# $COPILOT_RUNTIME_PORT) in the background, then execs Caddy in the
# foreground as PID 1 — Caddy is the process Railway health-checks and
# supervises; the runtime is reverse-proxied behind it (Caddyfile's
# /copilotkit route), never reachable directly. If the runtime dies, Caddy
# (and the container) keep running — /copilotkit then 502s rather than the
# whole site going down, an acceptable trade for a demo deploy.
set -eu

node /app/dist-server/index.js &

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
