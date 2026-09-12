/**
 * Auth0 tenant config for Screen 1 (web sign-in, W1). Read once at module
 * load — Vite inlines `import.meta.env.VITE_*` at build time, the
 * browser-safe counterpart to `vite.config.ts`'s server-side
 * `WEB_SERVICE_TOKEN` handling.
 *
 * No Auth0 tenant exists in this workspace yet. `AUTH_ENABLED` is what lets
 * local dev run without one — `SessionGate` becomes a no-op passthrough
 * while it's false, so nothing downstream needs to special-case "no
 * tenant configured" itself.
 */
export const AUTH0_DOMAIN = import.meta.env.VITE_AUTH0_DOMAIN as string | undefined
export const AUTH0_CLIENT_ID = import.meta.env.VITE_AUTH0_CLIENT_ID as string | undefined
export const AUTH0_AUDIENCE = import.meta.env.VITE_AUTH0_AUDIENCE as string | undefined

export const AUTH_ENABLED = Boolean(AUTH0_DOMAIN && AUTH0_CLIENT_ID)
