/**
 * Auth0 tenant config for the sign-in gate. Read once at module load —
 * Vite inlines `import.meta.env.VITE_*` at build time, the browser-safe
 * counterpart to `vite.config.ts`'s server-side `SERVICE_TOKEN` handling.
 *
 * `AUTH_ENABLED` is what lets local dev keep running against today's
 * persona-switcher demo mode, untouched, whenever these two are unset — which is the default everywhere but a deployment
 * that supplies them at build time. No `audience`: the backend keeps
 * authenticating with its own service token, this gate never issues or
 * checks a JWT.
 *
 * `VITE_AUTH0_DISABLED` (KATA-28) is a separate kill switch, off by
 * default: a deployment that already has a tenant configured (both values
 * above set) can still force the gate off entirely, e.g. a public demo
 * that wants today's no-login persona-switcher mode even with credentials
 * present. This UI flag alone does NOT make writes safe to expose — the
 * persona switcher's `X-Acting-Identity` is client-controlled either way
 * (`persona-store.ts`) and the proxy forwards it upstream regardless of
 * this gate. A deployment that sets this must also set the *runtime*
 * `AUTH0_DISABLED=true` (Caddyfile / vite.config.ts) so the proxy blocks
 * every mutating verb to `/api/*` and only reads (mock seeded data) stay
 * reachable without a login. Left unset, it changes nothing: `AUTH_ENABLED`
 * still follows the domain/client id pair exactly as before this flag
 * existed.
 */
export const AUTH0_DOMAIN = import.meta.env.VITE_AUTH0_DOMAIN as string | undefined
export const AUTH0_CLIENT_ID = import.meta.env.VITE_AUTH0_CLIENT_ID as string | undefined

const AUTH0_DISABLED = import.meta.env.VITE_AUTH0_DISABLED === 'true'

export const AUTH_ENABLED = !AUTH0_DISABLED && Boolean(AUTH0_DOMAIN && AUTH0_CLIENT_ID)
