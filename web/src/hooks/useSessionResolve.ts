import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '@/lib/api-client'

/** The core's real `PersonSummary` (`contracts/openapi.yaml`). */
export interface ResolvedSessionPerson {
  id: string
  display_name: string
  email: string
  is_operator: boolean
  role: string | null
}

/** Who is asking to be resolved: the Auth0 subject (or, under the e2e
 * bypass, the learner email itself) and the verified email to look up. */
export interface SessionIdentity {
  subject: string
  email: string
}

interface ResolveState {
  data: ResolvedSessionPerson | null
  isPending: boolean
  isError: boolean
  error: Error | null
}

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase()
}

const IDLE: ResolveState = { data: null, isPending: false, isError: false, error: null }

/**
 * Screen 1's happy path: once there is a verified email to act on, resolve
 * it against the roster via `POST /identities/resolve` — `platform: "web"`,
 * `external_id` the normalized email, `X-Acting-Identity: web:<subject>`.
 * A no-op while `identity` is null. The web app never writes identity
 * state itself; a miss surfaces as the same `403 unknown_identity` every
 * other surface gets. Each distinct `(subject, email)` pair resolves once.
 */
export function useSessionResolve(identity: SessionIdentity | null): ResolveState {
  const key = identity ? `${identity.subject}:${identity.email}` : null
  const [state, setState] = useState<ResolveState>(key ? { ...IDLE, isPending: true } : IDLE)
  const lastKey = useRef<string | null>(null)

  useEffect(() => {
    if (!identity || !key) {
      lastKey.current = null
      setState(IDLE)
      return
    }
    if (lastKey.current === key) return
    lastKey.current = key

    let cancelled = false
    setState({ ...IDLE, isPending: true })
    apiFetch<ResolvedSessionPerson>('/identities/resolve', {
      persona: { header: `web:${identity.subject}` },
      method: 'POST',
      body: { platform: 'web', external_id: normalizeEmail(identity.email) },
    })
      .then((data) => {
        if (!cancelled) setState({ data, isPending: false, isError: false, error: null })
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ data: null, isPending: false, isError: true, error: error as Error })
      })

    return () => {
      cancelled = true
    }
    // Deliberately keyed on `key` alone: `identity` is a fresh object
    // literal on every caller render (SessionGate builds one inline), so
    // depending on it directly would re-run this effect — and cancel the
    // in-flight fetch — on every unrelated re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return state
}
