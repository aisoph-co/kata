# web

Kata product-simulation UI — the AGCTM-56 mock's look: teal `KATA` wordmark,
four tabs, avatar persona menu — against the live API, EN or VI.

## Morning walkthrough

```bash
npm install                 # first run only
cp .env.example .env        # first run only
npm run demo                 # Postgres + migrate + seed ferry + API :8000 + web :5173
```

Open http://localhost:5173/en (or `/vi`) — lands on **Team context**.

1. **Team context** — Connect state + STREAM log; `/me/concept-graph`; three real `/topics` cards.
2. **Progress** — 4 stat tiles, 30-day chart from `GET /me/history`.
3. **Team** (managers only) — heatmap, adherence column, team-mean row.
4. **Connect** — 5 fake chat connectors, client-only simulation, no API calls.

**Developer** reveals **Backstage** and **All screens**. `npm run demo:down`
stops everything; `demo:real-llm` skips the stub grader.

**Sign-in gate** (AE-24): a doorman only — signed out shows a sign-in
screen, any Google account with a verified email gets in, the app then
runs exactly as above. Off by default (`npm run dev`, this walkthrough,
the e2e suite). To try it locally: `cp .env.auth0.example .env.auth0.local`,
fill in the two values, `npm run dev:auth0`. Sign out lives in the avatar
menu, only when the gate is on.

**e2e auth bypass** (AGCTM-64 finding #5): a test runner has no Auth0
account to log in with, so a deployment that sets `E2E_AUTH_BYPASS_TOKEN`
answers `GET /__e2e/session` with `{"email"}` for a request carrying that
same value in `X-E2E-Auth-Bypass` plus a seed learner in
`X-E2E-Learner-Email`, and the SPA lets it straight through as the gate's
pass. Unset (every non-test deployment) the route 404s and the gate is
untouched; `e2e/auth-bypass.spec.ts` pins both. Bypass headers are
stripped before `/api/*` reaches the core.

## Layout

```
src/                one file per screen/component (see pages/, components/)
scripts/            demo-up.sh, demo-down.sh, reset-demo-db.sh, e2e-loop.sh
e2e/                Playwright suite (global-setup waits for /health seed:ferry)
Dockerfile          node:22 build -> caddy:2-alpine runtime
Caddyfile           static + SPA fallback, /api/* proxy, /healthz
```

## Commands

```bash
npm run dev        # UI only, API not started
npm run dev:auth0   # same, with the sign-in gate on (needs .env.auth0.local)
npm run build       # tsc -b && vite build
npm run lint        # oxlint
npm run e2e          # Playwright suite, once (needs `npm run demo` running)
npm run e2e:loop     # same, 5x, fails on first red
```

## Docker / Caddy

```bash
docker build -t kata-web .
docker run -p 8080:8080 -e LEARNING_SERVICE_URL=http://host.docker.internal:8000 \
  -e LEARNING_SERVICE_TOKEN=dev kata-web
curl http://localhost:8080/healthz && curl http://localhost:8080/en   # both -> 200
E2E_BASE_URL=http://localhost:8080 npm run e2e   # suite through the container
```

## Never touches

| Item | Why |
|---|---|
| `LEARNING_SERVICE_TOKEN` in browser code | Injected by the Vite proxy (dev) or Caddy (prod) only |
| Client `Authorization` header | Caddy replaces it; never forwarded upstream |
| `E2E_AUTH_BYPASS_TOKEN` in browser code | The browser never learns it; only Caddy/Vite compare it, and the SPA only sees the 200/404 verdict |

## Env vars

| Var | Where | Purpose |
|---|---|---|
| `SERVICE_TOKEN` / `API_TARGET` | `web/.env` (dev) | Vite proxy bearer token / upstream, default `:8000` |
| `VITE_AUTH0_DOMAIN` / `VITE_AUTH0_CLIENT_ID` | build-time only (`web/.env.auth0.local` dev, Railway build args prod) | Sign-in gate. Unset (default) — no gate, demo mode as above |
| `LEARNING_SERVICE_URL` | container env (prod) | Caddy's `/api/*` upstream |
| `LEARNING_SERVICE_TOKEN` | container env (prod) | Bearer token Caddy injects into `/api/*` |
| `PORT` | container env (prod) | Caddy listen port, default `8080` |
| `E2E_AUTH_BYPASS_TOKEN` | container env (test deployments) / `web/.env` (dev) | Enables `/__e2e/session` for requests carrying the same value — see "e2e auth bypass" above. Unset = 404 = no bypass |
| `OPENROUTER_API_KEY` | `../.env` (API repo root) | Read by `demo-up.sh`, passed to the API only |
| `LEARNING_SEED`/`LEARNING_LLM`/`OPENROUTER_MODEL` | set by `demo-up.sh` | Passed to the API; `LEARNING_SEED=golden` for the synthetic fixture |

## Caveats

| Caveat | Detail |
|---|---|
| teach_back has no grader | 422 `no_grader` on a normal submit; "Just tell me" bypasses and reveals the explanation |
| `npm run e2e:loop` destroys demo state | Resets Postgres + reseeds before each of its 5 runs |
| Connect is a simulation | localStorage only, no API/OAuth — Team context reads its state |
| `auth-401.spec.ts` | Skipped when `E2E_BASE_URL` targets a container — needs a second dev server with a wrong token |
| Sign-in gate session isn't permanent | Survives a reload only until the cached token expires (SPA default 24h) or Auth0's session-check cookie lapses — after that, reload returns to the sign-in screen, since silent renewal needs a third-party cookie the deployed origin won't get |
