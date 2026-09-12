#!/command/with-contenv sh
# shellcheck shell=sh
# s6-rc longrun service (installed at /etc/s6-overlay/s6-rc.d/hermes-webui/run
# by the Dockerfile, modelled on the base image's own ../dashboard/run) —
# browser access to the exact same $HERMES_HOME the gateway (main-hermes) and
# CLI use: config.yaml, sessions db, and the hermes-kata plugin. There is no
# HTTP link between this and `gateway run`; both just read/write /opt/data
# (KATA-17). hermes-webui's own deps (pyyaml, cryptography) and source are
# baked into the image at build time; HERMES_WEBUI_AGENT_DIR/_PYTHON point it
# at the agent's own sealed venv instead of trying to discover/install one.
#
# with-contenv repopulates HOME from /init as /root. Reset it before
# dropping privileges so HOME-anchored state lands under /opt/data, same as
# ../dashboard/run and ../../docker/main-wrapper.sh do.
export HOME=/opt/data
export HERMES_WEBUI_AGENT_DIR=/opt/hermes
export HERMES_WEBUI_PYTHON=/opt/hermes/.venv/bin/python

cd /opt/kata/hermes-webui || exit 1

webui_host="${HERMES_WEBUI_HOST:-0.0.0.0}"
webui_port="${HERMES_WEBUI_PORT:-8787}"
export HERMES_WEBUI_HOST="$webui_host"
export HERMES_WEBUI_PORT="$webui_port"

# Skip the drop when already non-root (mirrors ../dashboard/run and
# ../../docker/main-wrapper.sh's `drop()`).
[ "$(id -u)" = 0 ] || exec /opt/hermes/.venv/bin/python server.py
exec s6-setuidgid hermes /opt/hermes/.venv/bin/python server.py
