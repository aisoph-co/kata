#!/usr/bin/env bash
# Idempotent Hermes instance config for the Kata Railway Hermes instance
# (deploy/kata/hermes). Safe to re-run: every call below is
# `hermes config set`, which overwrites rather than appends.
#
# See docs/superpowers/specs/2026-09-06-hermes-surface-spec.md §5, §7.
set -euo pipefail

PLATFORMS=(slack telegram discord whatsapp_cloud signal)

# Instance-level guardrails. One Hermes instance, one purpose (Kata) — no
# other tenant to carve a per-platform exception for.
hermes config set memory.memory_enabled false
hermes config set memory.user_profile_enabled false
hermes config set security.redact_secrets true
hermes config set terminal.backend modal

# Short transcript retention: the learner's real answer text and grades
# live in the learning service's own answer/review tables under the core's
# 90-day policy, so pruning Hermes's own copy sooner loses nothing.
hermes config set sessions.auto_prune true
hermes config set sessions.retention_days 14

# Web search (KATA-15): pin the instance-wide `web` toolset to the Exa
# backend. With EXA_API_KEY set (a Railway secret on this service), Hermes
# uses Exa's keyed SDK path instead of its anonymous, rate-limited keyless
# free tier.
hermes config set web.backend exa

# Toolset lockdown: every learner-facing platform gets exactly
# [learning, clarify] — never terminal/file/code_execution/browser/
# computer_use/delegation/or any other CONFIGURABLE_TOOLSETS entry. Add
# "web" only for a platform where content-freshness checks are wanted.
# Slack is that platform (KATA-15) — Exa-backed search for the Slack bot
# and, once its own platform_toolsets.api_server entry exists, the
# Copilotkit web bot (KATA-14) sharing this same instance-wide backend.
for platform in "${PLATFORMS[@]}"; do
  if [ "$platform" = "slack" ]; then
    hermes config set "platform_toolsets.${platform}" '["learning", "clarify", "web"]'
  else
    hermes config set "platform_toolsets.${platform}" '["learning", "clarify"]'
  fi
done
