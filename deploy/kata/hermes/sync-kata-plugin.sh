#!/usr/bin/env sh
# s6-overlay cont-init hook (installed at /etc/cont-init.d/50-sync-kata-plugin
# by the Dockerfile) — the base image's ENTRYPOINT dispatcher hands off to
# s6-overlay under a real PID 1, which runs every /etc/cont-init.d/* script
# to completion before starting the supervised `gateway run` (see
# Dockerfile). Runs on every boot, not just the first, so a rollback to an
# older image also rolls back the volume copy.
#
# Syncs the plugin baked into this image (/opt/kata/plugins/hermes-kata) onto
# the persistent volume with a delete-first copy, so a stale directory from
# an earlier manual deploy can never win: Hermes's real "user" plugin
# discovery sweep (hermes_cli/plugins_discovery.py::collect_directory_
# manifests, confirmed against a live hermes-v3, KATA-17 deploy
# verification) scans exactly `get_hermes_home() / "plugins"` — NOT
# `$HERMES_HOME/.hermes/plugins/` as this plugin's own README previously
# claimed (that path is never scanned at all; a plugin synced there is
# invisible to `hermes plugins list`/`enable`/doctor and never registers a
# single tool or hook, no matter how correct its code is). The 2026-09-10
# incident was a stale copy's handlers taking precedence over the current
# ones at this same, correct path. Delete-first, not overwrite-in-place, so
# a file removed upstream also disappears here — never leave a backup
# beside it (KATA-31).
set -eu

HOME_DIR="${HERMES_HOME:-/opt/data}"
DEST="$HOME_DIR/plugins/hermes-kata"

rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
cp -r /opt/kata/plugins/hermes-kata "$DEST"
find "$DEST" -name __pycache__ -type d -prune -exec rm -rf {} +
