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
runs exactly as above. Off by default (`npm run dev`, this walkthrough).
To try it locally: `cp .env.auth0.example .env.auth0.local`,
fill in the two values, `npm run dev:auth0`. Sign out lives in the avatar
menu, only when the gate is on.

**e2e auth bypass** (AGCTM-64 finding #5): a test runner has no Auth0
account to log in with, so a deployment that sets `E2E_AUTH_BYPASS_TOKEN`
answers `GET /__e2e/session` with `{"email"}` for a request carrying that
same value in `X-E2E-Auth-Bypass` plus a seed learner in
`X-E2E-Learner-Email`, and the SPA lets it straight through as the gate's
pass. Unset (every non-test deployment) the route 404s and the gate is
untouched. Bypass headers are stripped before `/api/*` reaches the core.

## Layout

```
src/                one file per screen/component (see pages/, components/)
server/             CopilotKit runtime for the in-app Kata bot (its own service)
scripts/            demo-up.sh, demo-down.sh, reset-demo-db.sh
Dockerfile          node:22 build -> caddy:2-alpine runtime
Caddyfile           static + SPA fallback, /api/* proxy, /healthz
```

## Commands

```bash
npm run dev        # UI only, API not started
npm run dev:auth0   # same, with the sign-in gate on (needs .env.auth0.local)
npm run build       # tsc -b && vite build
npm run lint        # oxlint
npm run server:dev   # CopilotKit runtime on :8090, watch mode
npm run test:server  # runtime identity tests (node --test)
```

## Docker / Caddy

```bash
docker build -t kata-web .
docker run -p 8080:8080 -e LEARNING_SERVICE_URL=http://host.docker.internal:8000 \
  -e LEARNING_SERVICE_TOKEN=dev kata-web
curl http://localhost:8080/healthz && curl http://localhost:8080/en   # both -> 200
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
| `VITE_COPILOTKIT_RUNTIME_URL` | build-time only | In-app Kata bot. Unset (default) — no popup |
| `HERMES_API_URL` / `HERMES_API_KEY` | runtime service env | Hermes OpenAI-compatible endpoint the runtime forwards every turn to |
| `AUTH0_DOMAIN` / `AUTH0_CLIENT_ID` | runtime service env | Verifies the caller's ID token against the tenant's JWKS |
| `WEB_BASE_URL` | runtime service env | The one origin the runtime accepts browser calls from |
| `LEARNING_SERVICE_URL` / `LEARNING_SERVICE_TOKEN` | runtime service env | AE-25 insight lane: the runtime's own calls to the learning service (`/me/*`, `/team/*`). Unset — insight lane off, popup stays Hermes-only |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | runtime service env | AE-25 insight lane's model. Unset — insight replies use a plain template instead of an LLM-phrased sentence (numbers are unaffected either way) |
| `OPENROUTER_API_KEY` | `../.env` (API repo root) | Read by `demo-up.sh`, passed to the API only |
| `LEARNING_SEED`/`LEARNING_LLM`/`OPENROUTER_MODEL` | set by `demo-up.sh` | Passed to the API; `LEARNING_SEED=golden` for the synthetic fixture |

## Caveats

| Caveat | Detail |
|---|---|
| teach_back has no grader | 422 `no_grader` on a normal submit; "Just tell me" bypasses and reveals the explanation |
| Connect is a simulation | localStorage only, no API/OAuth — Team context reads its state |
| Sign-in gate session isn't permanent | Survives a reload only until the cached token expires (SPA default 24h) or Auth0's session-check cookie lapses — after that, reload returns to the sign-in screen, since silent renewal needs a third-party cookie the deployed origin won't get |
