import { useAuth0 } from '@auth0/auth0-react'
import { useEffect, type ReactNode } from 'react'
import { useE2ESession } from '@/hooks/useE2ESession'
import { useSessionResolve, type SessionIdentity } from '@/hooks/useSessionResolve'
import { ApiError } from '@/lib/api-client'
import { AUTH_ENABLED } from '@/lib/auth-config'
import { confirmRole, resetRoleConfirm, useRoleConfirm } from '@/lib/role-confirm-store'
import { clearWebSession, setWebSession } from '@/lib/session-store'
import { RoleConfirm } from '@/pages/RoleConfirm'
import { RoleRequired } from '@/pages/RoleRequired'
import { SignIn } from '@/pages/SignIn'
import { SignInRefused } from '@/pages/SignInRefused'

/**
 * Screen 1 + Screen 2's gate (W1): sign in via Auth0, resolve the verified
 * email against the roster, confirm the resolved role, then either render
 * the app as that person or show a fixed refusal/blocking screen. A no-op
 * passthrough when Auth0 isn't configured for this deployment
 * (`AUTH_ENABLED`) — no tenant exists in this workspace yet.
 */
export function SessionGate({ children }: { children: ReactNode }) {
  if (!AUTH_ENABLED) return <>{children}</>
  return <RequireAuth0Session>{children}</RequireAuth0Session>
}

function RequireAuth0Session({ children }: { children: ReactNode }) {
  const auth0 = useAuth0()
  // Finding #5 (AGCTM-64): the server-granted e2e bypass. When it is
  // granted, the seed learner it names stands in for the Auth0 user: same
  // resolve call, same refusal on a miss, role taken as confirmed. Its
  // subject is the email itself, so every later call's
  // `X-Acting-Identity: web:<email>` is the `(web, <email>)` identity the
  // roster import created — the one thing the core can resolve. When the
  // bypass isn't granted (every real deployment), nothing below changes.
  const e2e = useE2ESession()
  const bypass = e2e.data ?? null
  const identity: SessionIdentity | null = bypass
    ? { subject: bypass.email, email: bypass.email }
    : auth0.isAuthenticated && auth0.user?.email_verified === true && auth0.user.email && auth0.user.sub
      ? { subject: auth0.user.sub, email: auth0.user.email }
      : null

  const resolve = useSessionResolve(identity)
  const subject = identity?.subject
  const resolved = resolve.data
  const roleConfirm = useRoleConfirm()
  const sessionConfirmedRole = resolved && roleConfirm.personId === resolved.id ? roleConfirm.role : null
  const confirmedRole = sessionConfirmedRole ?? (bypass && resolved ? resolved.role : null)

  // Keeps the resolved session live for downstream screens (W2-W4) for as
  // long as this gate is passed, only once a role is confirmed; clears it
  // and the confirmation together the moment the session isn't live, so
  // neither a stale identity nor a stale role survives for the next
  // visitor on the same browser.
  useEffect(() => {
    if (!resolved || !subject || !confirmedRole) return
    setWebSession({
      personId: resolved.id,
      displayName: resolved.display_name,
      email: resolved.email,
      isOperator: resolved.is_operator,
      role: confirmedRole,
      header: `web:${subject}`,
    })
    return () => {
      clearWebSession()
      resetRoleConfirm()
    }
  }, [resolved, subject, confirmedRole])

  // One round trip before anything else: is this browser an e2e run the
  // service has been told to let through? (A 404 answers within the same
  // origin — no visible delay for a real visitor.)
  if (e2e.isPending) return <SignIn status="loading" />

  if (!bypass) {
    if (auth0.isLoading) return <SignIn status="loading" />
    if (auth0.error) return <SignIn status="error" message={auth0.error.message} />
    if (!auth0.isAuthenticated) return <SignIn status="signed-out" />

    // email_verified: false never reaches the core at all (`identity` stays
    // null, so useSessionResolve never fires) — same refusal screen either way.
    if (auth0.user?.email_verified !== true) return <SignInRefused />
  }

  if (resolve.isError) {
    if (resolve.error instanceof ApiError && resolve.error.status === 403) {
      return <SignInRefused />
    }
    const message = resolve.error instanceof Error ? resolve.error.message : undefined
    return <SignIn status="error" message={message} />
  }

  if (!resolved) return <SignIn status="loading" />

  // Screen 2, failure path B: no role on record for this person at all —
  // blocked with an explicit prompt, never a silent default.
  if (!resolved.role) return <RoleRequired />

  // Screen 2, happy path: a role is on record but this session hasn't
  // confirmed it yet — confirm/change gate before anything else renders.
  if (!confirmedRole) {
    return (
      <RoleConfirm
        resolved={{ ...resolved, role: resolved.role }}
        onConfirm={(role) => confirmRole(resolved.id, role)}
      />
    )
  }

  return <>{children}</>
}
