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
 */
export const AUTH0_DOMAIN = import.meta.env.VITE_AUTH0_DOMAIN as string | undefined
export const AUTH0_CLIENT_ID = import.meta.env.VITE_AUTH0_CLIENT_ID as string | undefined

export const AUTH_ENABLED = Boolean(AUTH0_DOMAIN && AUTH0_CLIENT_ID)
