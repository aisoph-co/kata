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
# an earlier manual deploy can never win: Hermes's plugin manager loads every
# directory under $HERMES_HOME/.hermes/plugins/ (plugins/hermes-kata/README.md
# "Installing into the Kata Hermes instance"), and the 2026-09-10 incident
# was exactly a stale copy's handlers taking precedence over the current
# ones. Delete-first, not overwrite-in-place, so a file removed upstream
# also disappears here — never leave a backup beside it (KATA-31).
set -eu

HOME_DIR="${HERMES_HOME:-/opt/data}"
DEST="$HOME_DIR/.hermes/plugins/hermes-kata"

rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
cp -r /opt/kata/plugins/hermes-kata "$DEST"
find "$DEST" -name __pycache__ -type d -prune -exec rm -rf {} +
