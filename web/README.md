# web

Kata's web app. W1 built Screen 1 (sign-in) and Screen 2 (role
confirmation). W2 adds the two screens behind that gate: the quiz-taking
engine (`/reps`) and the personal dashboard (`/dashboard`, frame 09).
Topics/concept-map and the manager team view (W3, W4) land in their own
issues, on their own routes inside the same `AppShell`.

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

## Quiz-taking engine and dashboard (W2)

`/reps` renders `GET /me/next` one item at a time — a widget per `ItemKind`
(mcq/msq/self_rated/short_answer/teach_back) matching the core spec's
`response` shape table, confidence (1-5) captured before reveal, and a
"just tell me" bypass. `POST /me/reviews` grades it; a replayed submission
(same `idempotency_key`) comes back as a `409` whose body is the original
result, rendered exactly like a fresh `200`. `teach_back` has no automated
grader (`422 no_grader` on every real submission) so only the bypass path
is offered for it.

`/dashboard` reads `/me/progress` for the four tiles (retention, mastery,
calibration, bypass rate) and `/me/concept-graph` for the mastery-per-concept
table (names `/me/progress` doesn't carry). Two open gaps in the contract,
degraded rather than worked around or invented:

- **R3a** — `ProgressEntry` has no per-concept rep count yet, so that
  column always reads "—".
- **R3b** — there is no history/time-series endpoint, so the chart's 30-day
  "what Kata believes you know" line, the bypass annotation and its
  closing-question recovery, and the bypass-rate trend are all built from
  the seed's own `docs/seed/3-history/reviews.jsonl` (`src/data/`) — a
  scenario-specific shortcut for this fixed demo dataset, not a
  generalized mechanism a real learner's dashboard could draw from today.

## Layout

```
src/
  pages/       SignIn, SignInRefused, RoleRequired, RoleConfirm, Reps, Dashboard
  components/  SessionGate, AppShell, Auth0ProviderWithNavigate, reps/, dashboard/
  hooks/       useSessionResolve, useE2ESession, useApiResource (GET /me/*)
  lib/         api-client, auth-config, session-store, role-confirm-store,
               router (path-based, no dependency), quiz-types, bkt-replay, format
  data/        hugo-idempotency-history — the R3b seed-derived chart fixture
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
