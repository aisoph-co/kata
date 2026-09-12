import { useEffect, useState } from 'react'
import { AUTH_ENABLED } from '@/lib/auth-config'

/** What `/__e2e/session` grants: the seed learner this browser may act as. */
export interface E2ESession {
  email: string
}

interface E2EState {
  data: E2ESession | null
  isPending: boolean
}

/**
 * Finding #5 (AGCTM-64): the e2e auth bypass, read once per page load and
 * only when Screen 1's real gate is on (`AUTH_ENABLED`). The decision is
 * always the server's, never this code's: Caddy (prod) / the Vite dev
 * plugin (`vite.config.ts`) answer 200 + the learner email only when the
 * deployment has `E2E_AUTH_BYPASS_TOKEN` set and the request carried it —
 * the test runner attaches it as an extra header on every request the
 * browser makes. A 404 (variable unset, wrong token, no header) or any
 * failure means "no bypass," and the normal Auth0 path runs unchanged.
 */
export function useE2ESession(): E2EState {
  const [state, setState] = useState<E2EState>({ data: null, isPending: AUTH_ENABLED })

  useEffect(() => {
    if (!AUTH_ENABLED) {
      setState({ data: null, isPending: false })
      return
    }

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
