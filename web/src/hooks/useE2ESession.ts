import { useQuery } from '@tanstack/react-query'
import { AUTH_ENABLED } from '@/lib/auth-config'

/** What `/__e2e/session` grants: the seed learner this browser may act as. */
export interface E2ESession {
  email: string
}

/**
 * AGCTM-64 finding #5: the e2e auth bypass, read once per page load and
 * only when Screen 1's real gate is on (`AUTH_ENABLED`; the demo
 * persona-switcher mode has nothing to bypass). The decision is the
 * server's, never this code's: Caddy (prod) / the Vite dev plugin answer
 * 200 + the learner email only when the deployment has
 * E2E_AUTH_BYPASS_TOKEN set and the request carried it — the test runner
 * attaches it as an extra HTTP header on every request the browser makes.
 * A 404 (the variable unset, a wrong token, no header) or any failure
 * means "no bypass" and the normal Auth0 path runs unchanged.
 */
export function useE2ESession() {
  return useQuery({
    queryKey: ['e2e-session'],
    queryFn: async (): Promise<E2ESession | null> => {
      try {
        const res = await fetch('/__e2e/session')
        if (!res.ok) return null
        const body = (await res.json()) as { email?: unknown }
        return typeof body.email === 'string' && body.email ? { email: body.email } : null
      } catch {
        return null
      }
    },
    enabled: AUTH_ENABLED,
    retry: false,
    staleTime: Infinity,
  })
}
