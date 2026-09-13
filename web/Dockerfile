# Kata web app. Static SPA built by Vite, served by Caddy, which also
# proxies /api/* to the learning service and injects the service token
# server-side (spec: PLAN_10). Configured entirely through env vars at
# runtime — no secrets baked into the image.
#
# KATA-14 (demo round): also builds and runs W10's CopilotKit runtime
# (`web/server`) in the same container, Caddy reverse-proxying /copilotkit
# to it — one service, one deploy, and the popup's runtimeUrl stays the
# same-origin, no-CORS absolute URL CopilotKit's own docs ask for. A
# dedicated service is the cleaner long-term shape; this is the fastest
# correct path to a working demo (see PR discussion).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# AE-24: sign-in gate config. Vite inlines VITE_* at build time, so these
# must be build args, not container env — an unset pair (default) leaves
# the gate off and the build byte-for-byte the same as before. The host
# (Railway) supplies the values as build args; no runtime env var needed.
ARG VITE_AUTH0_DOMAIN
ARG VITE_AUTH0_CLIENT_ID
# KATA-28: same build-arg treatment as the pair above. Pair it with the
# AUTH0_DISABLED *container* env var (set at deploy time, not here) for the
# gate to actually stay off *and* read-only — this ARG alone only affects
# the SPA's own UI, not what the Caddyfile lets through. Unset (default),
# no effect either way.
ARG VITE_AUTH0_DISABLED
# KATA-14: same convention — the popup's absolute runtimeUrl, inlined at
# build time. Unset (the default) leaves the popup off, same as today.
ARG VITE_COPILOTKIT_RUNTIME_URL
# KATA-28: on/off switch for the popup, paired with the runtime URL above.
# Unset (default), no effect — popup follows VITE_COPILOTKIT_RUNTIME_URL.
ARG VITE_COPILOTKIT_ENABLED
RUN npm run build
RUN npm run server:build

FROM caddy:2-alpine
# The runtime is plain compiled JS (no native deps beyond what npm already
# resolved) — Alpine's own nodejs package is enough, no separate Node image
# layer needed.
RUN apk add --no-cache nodejs
WORKDIR /app
COPY --from=build /app/dist /usr/share/caddy
COPY --from=build /app/dist-server ./dist-server
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json
COPY Caddyfile /etc/caddy/Caddyfile
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV PORT=8080
ENV COPILOT_RUNTIME_PORT=8090
EXPOSE 8080
ENTRYPOINT ["/docker-entrypoint.sh"]
