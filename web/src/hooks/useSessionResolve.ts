import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'

/** The core's real `PersonSummary` (`learning_service/identity/schemas.py`) —
 * richer than the demo persona bar's local copy in `useResolvedIdentity.ts`
 * (that one predates Contract change #8's `role` field; not touched here,
 * out of scope for W1). */
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

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase()
}

/**
 * Screen 1's happy path: once there is a verified email to act on, resolve
 * it against the roster via `POST /identities/resolve` — `platform: "web"`,
 * `external_id` the normalized email, `X-Acting-Identity: web:<subject>`.
 * Disabled (never called) while `identity` is null. The web app never
 * writes identity state itself; a miss surfaces as the same
 * `403 unknown_identity` every other surface gets.
 */
export function useSessionResolve(identity: SessionIdentity | null) {
  const subject = identity?.subject
  const email = identity?.email

  return useQuery({
    queryKey: ['session-resolve', subject, email],
    queryFn: () =>
      apiFetch<ResolvedSessionPerson>('/identities/resolve', {
        persona: { header: `web:${subject}` },
        method: 'POST',
        body: { platform: 'web', external_id: normalizeEmail(email!) },
      }),
    enabled: !!email && !!subject,
    retry: false,
    staleTime: Infinity,
  })
}
