# Hermes gateway for the Kata stack, with the Modal SDK and the hermes-kata
# plugin baked in.
#
# Why a derived image: the published image seals /opt/hermes and disables
# lazy dependency installs (HERMES_DISABLE_LAZY_INSTALLS=1), and `modal` is not
# part of its bundled extras — so `terminal.backend: modal` cannot install its
# SDK at first use. Bake the exact version Hermes' lazy_deps would have picked.
#
# Pinned to the image index digest so Railway and laptops build the same thing;
# bump the digest deliberately (docker buildx imagetools inspect
# nousresearch/hermes-agent:latest).
FROM nousresearch/hermes-agent:latest@sha256:40d2b9022428c236dba6ea23ee8b56367cea6880eda1aa302428ee0148414e79

ARG MODAL_VERSION=1.3.4
RUN uv pip install --python /opt/hermes/.venv/bin/python "modal==${MODAL_VERSION}" \
    && /opt/hermes/.venv/bin/python -c "import modal; print('modal', modal.__version__)"

# Bake the hermes-kata plugin and its pinned tool catalog into the image, so
# a merge under plugins/hermes-kata/ ships on the next deploy with no volume
# step (KATA-31 — was `railway ssh` + `tar`, the wrong loop on build day).
# /opt/data is the volume mount and shadows anything the image puts there,
# so these live under /opt/kata instead. Build context must be the repo
# root for this COPY to see plugins/ — set RAILWAY_DOCKERFILE_PATH on the
# Railway service to this file's path, not its directory.
COPY plugins/hermes-kata /opt/kata/plugins/hermes-kata
COPY deploy/kata/hermes/tools.json /opt/kata/tools.json

# KATA-15: bake apply-config.sh into the image too, so a fresh deploy always
# ships the script that matches it instead of whatever's left on the /opt/data
# volume from an older image. /opt/kata, never /opt/data — see above.
COPY deploy/kata/hermes/apply-config.sh /opt/kata/apply-config.sh

# s6-overlay cont-init hooks: run once per boot, in numeric order, before
# `gateway run` starts. hermes-v3 has no guarantee its volume survives a
# redeploy/recreate (KATA-17 deploy verification), so config.yaml settings
# and the plugin's enabled state can't depend on a one-off manual step
# having already run against whatever volume happens to be attached —
# apply-config.sh (config + `plugins.enabled`) runs first, then
# sync-kata-plugin.sh syncs the baked plugin onto the volume with a
# delete-first copy so a stale directory can never win (sync-kata-plugin.sh
# has the full story, including the 2026-09-10 incident).
COPY --chmod=755 deploy/kata/hermes/apply-config.sh /etc/cont-init.d/49-apply-kata-config
COPY --chmod=755 deploy/kata/hermes/sync-kata-plugin.sh /etc/cont-init.d/50-sync-kata-plugin

# Everything else (config.yaml, .env, sessions, cron state) lives on the
# /opt/data volume; see ../README.md and apply-config.sh.

# Run the gateway by default (the upstream image's empty CMD starts the
# interactive CLI). The image ENTRYPOINT dispatcher stays in place; under a
# real PID 1 it hands off to s6-overlay, which supervises the gateway.
CMD ["gateway", "run"]
