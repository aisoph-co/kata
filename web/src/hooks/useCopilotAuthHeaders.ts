import { useAuth0 } from '@auth0/auth0-react'
import { useEffect, useState } from 'react'
import { AUTH_ENABLED } from '@/lib/auth-config'

/**
 * The bearer credential the popup attaches to every runtime call so the
 * runtime — never the browser — decides who the turn runs as. Under a real
 * Auth0 session this is the raw ID token (a signed JWT the runtime verifies
 * against the tenant's JWKS, `server/identity.ts`).
 *
 * With the gate off (`AUTH_ENABLED` false — local dev, demo mode) there is
 * no token to fetch and this adds nothing; the e2e bypass headers already
 * travel with every request the harness makes on that browser context
 * (`useE2ESession`), and the runtime trusts that same pair.
 *
 * Returns `undefined` while a real session is still fetching its token —
 * the caller should hold the popup back rather than send a request with no
 * Authorization header and collect a 401 — and `{}` once nothing more is
 * needed.
 */
export function useCopilotAuthHeaders(): Record<string, string> | undefined {
  const auth0 = useAuth0()
  const [idToken, setIdToken] = useState<string | null>(null)
  const needsToken = AUTH_ENABLED && auth0.isAuthenticated

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
    // on the one primitive that actually changes avoids an effect loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsToken])

  if (!needsToken) return {}
  if (!idToken) return undefined
  return { Authorization: `Bearer ${idToken}` }
}
