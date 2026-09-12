#!/usr/bin/env sh
# Apply the Kata Hermes settings to the $HERMES_HOME on the mounted volume.
# Idempotent: runs `hermes config set` for every key, which is the supported
# way to edit config.yaml (a stray indent from a hand edit can break the gateway).
#
# Run inside the container:
#   Railway:  railway ssh --service hermes -- sh /opt/data/apply-config.sh
#             (pipe it in first: railway ssh --service hermes -- sh -s < deploy/kata/hermes/apply-config.sh)
#   Compose:  docker compose run --rm hermes sh /opt/kata/apply-config.sh
#
# TERMINAL_BACKEND: modal on Railway (no Docker daemon there), docker on a VPS/laptop.
#
# sessions.* / platform_toolsets.* below are the Hermes surface spec's
# toolset lockdown (docs/superpowers/specs/2026-09-06-hermes-surface-spec.md
# §5): every learner-facing platform gets {learning, clarify} and nothing
# else, and sessions are pruned after 14 days instead of the 90-day default.
# KATA-15 adds "web" for slack only — the one platform where a learner asks
# about something newer than the seeded sources. web.backend=exa points that
# toolset at Exa's keyed SDK (EXA_API_KEY, a Railway secret on this service)
# instead of Hermes' anonymous, rate-limited keyless tier.
# plugins/hermes-kata/tests/test_toolset_lockdown.py runs this file against a
# stubbed `hermes` and asserts the property, without a live Hermes.
set -eu

BACKEND="${TERMINAL_BACKEND:-modal}"
MODEL="${HERMES_MODEL:-openai/gpt-5.6-luna}"

# The image seeds config.yaml from cli-config.yaml.example, which carries no
# _config_version, so every later boot warns "config predates version 12". The
# seeded file *is* the current shape, so stamp it with the running version's
# own number (read from DEFAULT_CONFIG — never hard-code it, a lower value makes
# the boot migrator replay every migration since).
CONFIG_VERSION="$(cd /opt/hermes 2>/dev/null && /opt/hermes/.venv/bin/python -c \
  'from hermes_cli.config import DEFAULT_CONFIG; print(DEFAULT_CONFIG.get("_config_version", 1))' 2>/dev/null || echo 1)"

set -- \
  "_config_version=${CONFIG_VERSION}" \
  "model.provider=openrouter" \
  "model.default=${MODEL}" \
  "terminal.backend=${BACKEND}" \
  "terminal.modal_mode=direct" \
  "terminal.timeout=180" \
  "terminal.container_persistent=true" \
  "memory.memory_enabled=false" \
  "memory.user_profile_enabled=false" \
  "security.redact_secrets=true" \
  "sessions.auto_prune=true" \
  "sessions.retention_days=14" \
  "web.backend=exa" \
  'platform_toolsets.slack=["learning","clarify","web"]' \
  'platform_toolsets.telegram=["learning","clarify"]' \
  'platform_toolsets.discord=["learning","clarify"]' \
  'platform_toolsets.whatsapp_cloud=["learning","clarify"]' \
  'platform_toolsets.signal=["learning","clarify"]'

for kv in "$@"; do
  key="${kv%%=*}"
  value="${kv#*=}"
  hermes config set --force "$key" "$value"
done

hermes config get terminal.backend
