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

# Bake the hermes-kata plugin into the image, so a merge under
# plugins/hermes-kata/ ships on the next deploy with no volume step.
# /opt/data is the volume mount and shadows anything the image puts there,
# so this lives under /opt/kata instead. Build context must be the repo root
# for this COPY to see plugins/ — RAILWAY_DOCKERFILE_PATH on the Railway
# service points Railway at this file from there.
#
# tools.json is not copied: the plugin vendors its own frozen catalog at
# plugins/hermes-kata/hermes_kata/tools.json and only prefers $KATA_TOOLS_JSON
# when that variable is set (hermes_kata/catalog.py). A second copy in this
# directory would be the transcription that module exists to avoid.
COPY plugins/hermes-kata /opt/kata/plugins/hermes-kata

# s6-overlay cont-init hook: runs once per boot, before `gateway run`
# starts, and syncs the baked plugin above onto the volume with a
# delete-first copy so a stale directory can never win (sync-kata-plugin.sh
# has the full story).
COPY --chmod=755 deploy/kata/hermes/sync-kata-plugin.sh /etc/cont-init.d/50-sync-kata-plugin

# Everything else (config.yaml, .env, sessions, cron state) lives on the
# /opt/data volume; see deploy/kata/apply-config.sh.

# Run the gateway by default (the upstream image's empty CMD starts the
# interactive CLI). The image ENTRYPOINT dispatcher stays in place; under a
# real PID 1 it hands off to s6-overlay, which supervises the gateway.
# Never set a Railway start command on this service — the override replaces
# PID 1 and the container dies seconds after "Mounting volume" with no logs.
CMD ["gateway", "run"]
