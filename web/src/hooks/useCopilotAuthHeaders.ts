import { useAuth0 } from '@auth0/auth0-react'
import { useEffect, useState } from 'react'
import { AUTH_ENABLED } from '@/lib/auth-config'
import type { WebSession } from '@/lib/session-store'

/**
 * The bearer credential the popup attaches to every runtime call so the
 * runtime — never the browser — can stamp the acting identity (W10's "one
 * real design point"). Under a real Auth0 session this is the raw ID token
 * (a signed JWT the runtime verifies against the tenant's JWKS); the e2e
 * bypass has no Auth0 session to fetch a token from, but its own headers
 * travel with every request the test harness makes on this browser context
 * (`useE2ESession`'s doc comment) — this hook adds nothing in that case and
 * lets those headers do the work.
 *
 * Returns `undefined` while a real session is still fetching its token (the
 * caller should not render the popup yet — sending a request with no
 * Authorization header at all would just get a 401), `{}` once nothing more
 * is needed (no session, or the e2e path).
 */
export function useCopilotAuthHeaders(session: WebSession | null): Record<string, string> | undefined {
  const auth0 = useAuth0()
  const [idToken, setIdToken] = useState<string | null>(null)
  const needsToken = Boolean(session) && AUTH_ENABLED && auth0.isAuthenticated

  useEffect(() => {
    if (!needsToken) {
      setIdToken(null)
      return
    }
    let cancelled = false
    auth0
      .getIdTokenClaims()
      .then((claims) => {
        if (!cancelled) setIdToken(claims?.__raw ?? null)
      })
      .catch(() => {
        if (!cancelled) setIdToken(null)
      })
    return () => {
      cancelled = true
    }
    // `auth0` is a fresh object every render (the SDK's own contract); keying
    // on the two primitives that actually change avoids an effect loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsToken])

  if (!session) return undefined
  if (!needsToken) return {}
  if (!idToken) return undefined
  return { Authorization: `Bearer ${idToken}` }
}
