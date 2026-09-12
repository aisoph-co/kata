/**
 * Screen 1's fixed refusal screen — failure path A: the Auth0 profile's
 * email doesn't resolve to any roster person (`403 unknown_identity`), or
 * `email_verified` is false. No session is created, and nothing here
 * writes to the identity table — resolution only ever reads the roster
 * import. Mirrors Hermes's unknown-identity refusal exactly, not a
 * web-specific one.
 *
 * Reachable from the e2e-bypass path too, which may have no Auth0 tenant
 * configured at all — `onBack` is supplied by the caller (real Auth0
 * logout, or just a reload under the bypass) rather than this component
 * calling `useAuth0()` itself, so it never depends on an `Auth0Provider`
 * being mounted.
 */
export function SignInRefused({ onBack }: { onBack: () => void }) {
  return (
    <div className="gate-screen">
      <div className="gate-card gate-card--dashed" data-testid="sign-in-refused">
        <h2 className="gate-title">You&rsquo;re not set up yet</h2>
        <p className="gate-blurb">
          You&rsquo;re not set up as a Kata learner yet — ask your team admin for an invite.
        </p>
        <button data-testid="sign-in-refused-retry" onClick={onBack}>
          Back to sign-in
        </button>
      </div>
    </div>
  )
}
