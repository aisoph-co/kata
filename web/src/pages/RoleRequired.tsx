import { useAuth0 } from '@auth0/auth0-react'

/**
 * Screen 2's failure path B: this person resolved fine (Screen 1 passed)
 * but has no `role` on record — a roster import (contract change #8) that
 * ran without one. No silent default, no "unknown" persona, nothing to
 * confirm — a fixed, explicit prompt, and the app never renders past this
 * until a roster re-import sets the role. Shaped like `SignInRefused`, but
 * this is a role gap, not an identity one.
 */
export function RoleRequired() {
  const { logout } = useAuth0()

  return (
    <div className="gate-screen">
      <div className="gate-card gate-card--dashed" data-testid="role-required">
        <h2 className="gate-title">No role on record</h2>
        <p className="gate-blurb">
          Your account doesn&rsquo;t have a role yet, so we can&rsquo;t pick your topics — ask your
          team admin to set one and sign in again.
        </p>
        <button
          data-testid="role-required-back"
          onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
        >
          Back to sign-in
        </button>
      </div>
    </div>
  )
}
