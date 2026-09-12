import { useEffect, useState } from 'react'

/** What `/__e2e/session` grants: the seed learner this browser may act as. */
export interface E2ESession {
  email: string
}

interface E2EState {
  data: E2ESession | null
  isPending: boolean
}

/**
 * Finding #5 (AGCTM-64): the e2e auth bypass, read once per page load.
 * Checked unconditionally — independent of whether an Auth0 tenant is
 * configured for this deployment (`AUTH_ENABLED`), since a test/CI
 * deployment may set `E2E_AUTH_BYPASS_TOKEN` with no tenant to log into at
 * all. The decision is always the server's, never this code's: Caddy
 * (prod) / the Vite dev plugin (`vite.config.ts`) answer 200 + the learner
 * email only when the deployment has `E2E_AUTH_BYPASS_TOKEN` set and the
 * request carried it — the test runner attaches it as an extra header on
 * every request the browser makes. A 404 (variable unset, wrong token, no
 * header) or any failure means "no bypass."
 */
export function useE2ESession(): E2EState {
  const [state, setState] = useState<E2EState>({ data: null, isPending: true })

  useEffect(() => {
    let cancelled = false
    fetch('/__e2e/session')
      .then(async (res) => {
        if (!res.ok) return null
        const body = (await res.json()) as { email?: unknown }
        return typeof body.email === 'string' && body.email ? { email: body.email } : null
      })
      .catch(() => null)
      .then((data) => {
        if (!cancelled) setState({ data, isPending: false })
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}
