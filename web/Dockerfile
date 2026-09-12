# Kata web app (D1): node build -> caddy, serving the SPA through the
# Caddyfile that ships alongside it (static assets + /api/* proxy +
# /__e2e/session, see Caddyfile). Build root is `web/` (Railway
# `--path-as-root`), so paths below are relative to this directory.

FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /usr/share/caddy
COPY Caddyfile /etc/caddy/Caddyfile
