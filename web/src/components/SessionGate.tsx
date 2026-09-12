import { useAuth0 } from '@auth0/auth0-react'
import type { ReactNode } from 'react'
import { useE2ESession } from '@/hooks/useE2ESession'
import { AUTH_ENABLED } from '@/lib/auth-config'
import { SignIn } from '@/pages/SignIn'

/**
 * A doorman, not an authorisation system: signed out → the sign-in screen
 * and nothing else; signed in with any Google account whose email Auth0
 * reports verified → the app, unchanged, still running in its existing
 * demo/persona-switcher mode (no roster lookup, no role confirmation, no
 * refusal screen — AE-24 deliberately narrowed this from the earlier W1/W2
 * design). A no-op passthrough when Auth0 isn't configured for this
 * deployment (`AUTH_ENABLED`) — no tenant is baked into the build, so
 * local dev and every existing e2e test keep today's behaviour, untouched.
 */
export function SessionGate({ children }: { children: ReactNode }) {
  if (!AUTH_ENABLED) return <>{children}</>
  return <RequireAuth0Session>{children}</RequireAuth0Session>
}

function RequireAuth0Session({ children }: { children: ReactNode }) {
  const auth0 = useAuth0()
  // AGCTM-64 finding #5: the server-granted e2e bypass. When granted, the
  // suite is let straight through to the app — same as a real sign-in,
  // minus Auth0 (there's no tenant account for a test runner to log into).
  // When it isn't granted (every real deployment), nothing below changes.
  const e2e = useE2ESession()

  if (e2e.isPending) return <SignIn status="loading" />
  if (e2e.data) return <>{children}</>

  if (auth0.isLoading) return <SignIn status="loading" />
  if (auth0.error) return <SignIn status="error" message={auth0.error.message} />
  if (!auth0.isAuthenticated) return <SignIn status="signed-out" />
  // Doorman only: any authenticated Google account with a verified email
  // gets in — no separate refusal screen. An unverified email is still not
  // a "sign in" action away from anything different (Auth0 already has a
  // session for this account, so `loginWithRedirect` would just bounce
  // straight back here) — offer a way out instead of a dead-end loop.
  // PersonaMenu's sign-out is unreachable from here (it's inside the gate).
  if (auth0.user?.email_verified !== true) return <SignIn status="unverified" />

  return <>{children}</>
}
