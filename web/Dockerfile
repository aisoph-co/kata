# Kata web app. Static SPA built by Vite, served by Caddy, which also
# proxies /api/* to the learning service and injects the service token
# server-side (spec: PLAN_10). Configured entirely through env vars at
# runtime — no secrets baked into the image.
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
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /usr/share/caddy
COPY Caddyfile /etc/caddy/Caddyfile

ENV PORT=8080
EXPOSE 8080
