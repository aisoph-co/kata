# web

Kata's web app. This issue (W1) builds Screen 1 (sign-in) and Screen 2
(role confirmation) only — everything past that gate (topics/concept-map,
quiz-taking, dashboard, team view) lands in its own issue.

## Sign-in

Auth0 (Slack connection if configured for the tenant, Google always
available). On return with a verified email, the app calls
`POST /identities/resolve` with `{platform: "web", external_id: <normalized
email>}` and `X-Acting-Identity: web:<auth0 subject>` — it never writes
identity state itself. An unmatched or unverified email gets a fixed
refusal screen, no session created.

No Auth0 tenant is configured in this workspace yet: unset
`VITE_AUTH0_DOMAIN`/`VITE_AUTH0_CLIENT_ID` (see `.env.example`) makes
`SessionGate` a no-op passthrough, so local dev runs without one.

## e2e auth bypass (finding #5, AGCTM-64)

A test runner has no Auth0 account to log in with, so a deployment that
sets `E2E_AUTH_BYPASS_TOKEN` answers `GET /__e2e/session` with `{"email"}`
for any request carrying the same value in `X-E2E-Auth-Bypass` plus a seed
learner in `X-E2E-Learner-Email`; the SPA then resolves that email through
the normal `POST /identities/resolve` and treats the resolved role as
confirmed. Without the variable (every non-test deployment) the route is a
404 for everyone and Screen 1 is untouched. The bypass headers are
stripped before `/api/*` reaches the core (see `Caddyfile` / `vite.config.ts`).

## Commands

```bash
npm install
npm run dev     # UI only, core not started — the sign-in gate stays a no-op without Auth0 env vars
npm run build   # tsc -b && vite build
npm test        # vitest
```

## Layout

```
src/
  pages/       SignIn, SignInRefused, RoleRequired, RoleConfirm
  components/  SessionGate (the gate itself), Auth0ProviderWithNavigate
  hooks/       useSessionResolve (POST /identities/resolve), useE2ESession
  lib/         api-client, auth-config, session-store, role-confirm-store
Caddyfile      prod: static + SPA fallback, /api/* proxy, /__e2e/session
vite.config.ts dev: same /api proxy + /__e2e/session, as a dev-server plugin
```

## Env vars

| Var | Where | Purpose |
|---|---|---|
| `VITE_AUTH0_DOMAIN` / `VITE_AUTH0_CLIENT_ID` / `VITE_AUTH0_AUDIENCE` | build-time | Screen 1 sign-in. Unset today — the gate is a no-op passthrough |
| `WEB_SERVICE_TOKEN` | dev server / container env | The `/api/*` proxy's bearer token, injected server-side only |
| `LEARNING_SERVICE_URL` | dev server / container env | `/api/*` proxy upstream |
| `E2E_AUTH_BYPASS_TOKEN` | container env (test deployments) / `web/.env` (dev) | Enables `/__e2e/session` — see above. Unset = 404 = no bypass |
| `PORT` | container env (prod) | Caddy listen port, default `8080` |
