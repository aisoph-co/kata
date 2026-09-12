/**
 * Shown when there is no way to authenticate a real visitor at all: no
 * Auth0 tenant configured (`AUTH_ENABLED` false) and no e2e bypass granted
 * either. A misconfigured deployment must fail closed — this screen is
 * what stands in for the sign-in gate instead of silently rendering the
 * app for anyone, which unconditionally passing everyone through would do.
 * The e2e bypass (`SessionGate`) is checked before this and works with or
 * without a configured tenant, so this only ever shows for a real visitor
 * hitting a deployment that isn't ready yet.
 */
export function SignInUnavailable() {
  return (
    <div className="gate-screen">
      <div className="gate-card gate-card--dashed" data-testid="sign-in-unavailable">
        <h2 className="gate-title">Sign-in isn&rsquo;t set up yet</h2>
        <p className="gate-blurb">
          This deployment doesn&rsquo;t have sign-in configured yet, so nobody can get in right now
          — check back once it is, or ask your team admin.
        </p>
      </div>
    </div>
  )
}
