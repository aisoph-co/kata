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
import { SignInUnavailable } from '@/pages/SignInUnavailable'

/**
 * Screen 1 + Screen 2's gate (W1). The e2e bypass (finding #5) is checked
 * first and unconditionally — it must work whether or not this deployment
 * has an Auth0 tenant configured at all, since a test/CI deployment may set
 * `E2E_AUTH_BYPASS_TOKEN` with no tenant to log into. Only once no bypass
 * is granted does whether Auth0 is configured (`AUTH_ENABLED`) matter: with
 * it, a real visitor goes through Auth0; without it, there is no way to
 * authenticate anyone at all, so this blocks with a fixed screen rather
 * than rendering the app for anyone — a misconfigured deployment fails
 * closed, never open.
 */
export function SessionGate({ children }: { children: ReactNode }) {
  const e2e = useE2ESession()

  if (e2e.isPending) return <SignIn status="loading" />

  if (e2e.data) {
    const bypassIdentity: SessionIdentity = { subject: e2e.data.email, email: e2e.data.email }
    // No Auth0 session to log out of under the bypass (there may be no
    // Auth0Provider mounted at all) — a reload just re-runs this same
    // e2e-bypass check, which is all "back to sign-in" can mean here.
    return (
      <ResolveAndConfirm identity={bypassIdentity} bypass onBack={() => window.location.reload()}>
        {children}
      </ResolveAndConfirm>
    )
  }

  if (!AUTH_ENABLED) return <SignInUnavailable />

  return <RequireAuth0Session>{children}</RequireAuth0Session>
}

function RequireAuth0Session({ children }: { children: ReactNode }) {
  const auth0 = useAuth0()

  if (auth0.isLoading) return <SignIn status="loading" />
  if (auth0.error) return <SignIn status="error" message={auth0.error.message} />
  if (!auth0.isAuthenticated) return <SignIn status="signed-out" />

  const onBack = () => auth0.logout({ logoutParams: { returnTo: window.location.origin } })

  // email_verified: false gets the same fixed refusal as an unknown
  // identity — never reaches `POST /identities/resolve` at all.
  if (auth0.user?.email_verified !== true || !auth0.user.email || !auth0.user.sub) {
    return <SignInRefused onBack={onBack} />
  }

  return (
    <ResolveAndConfirm identity={{ subject: auth0.user.sub, email: auth0.user.email }} onBack={onBack}>
      {children}
    </ResolveAndConfirm>
  )
}

/**
 * Screen 1's resolve + Screen 2's role confirmation — shared by the real
 * Auth0 path and the e2e bypass path alike, so both go through the same
 * `POST /identities/resolve` and the same refusal/role-required behavior.
 * Only the bypass path (`bypass: true`) treats the resolved role as
 * already confirmed (finding #5); a real sign-in still needs an explicit
 * confirm/change click every session.
 */
function ResolveAndConfirm({
  identity,
  bypass = false,
  onBack,
  children,
}: {
  identity: SessionIdentity
  bypass?: boolean
  onBack: () => void
  children: ReactNode
}) {
  const resolve = useSessionResolve(identity)
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
    if (!resolved || !confirmedRole) return
    setWebSession({
      personId: resolved.id,
      displayName: resolved.display_name,
      email: resolved.email,
      isOperator: resolved.is_operator,
      role: confirmedRole,
      header: `web:${identity.subject}`,
    })
    return () => {
      clearWebSession()
      resetRoleConfirm()
    }
  }, [resolved, confirmedRole, identity.subject])

  if (resolve.isError) {
    if (resolve.error instanceof ApiError && resolve.error.status === 403) {
      return <SignInRefused onBack={onBack} />
    }
    const message = resolve.error instanceof Error ? resolve.error.message : undefined
    return <SignIn status="error" message={message} />
  }

  if (!resolved) return <SignIn status="loading" />

  // Screen 2, failure path B: no role on record for this person at all —
  // blocked with an explicit prompt, never a silent default.
  if (!resolved.role) return <RoleRequired onBack={onBack} />

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
