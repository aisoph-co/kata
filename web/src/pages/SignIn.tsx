import { useAuth0 } from '@auth0/auth0-react'

type Status = 'loading' | 'signed-out' | 'error'

/**
 * Screen 1's landing page for a signed-out visitor — offers Auth0 login
 * (Slack connection if configured for the tenant, Google always available;
 * both are Auth0 Universal Login's choice, not this component's) and never
 * guesses or pre-fills an identity.
 *
 * Also covers the loading states (Auth0 itself, then the resolve call) and
 * the failure path — Auth0 error or the visitor cancels: back here with a
 * retry action, no partial session, no stack trace.
 */
export function SignIn({ status, message }: { status: Status; message?: string }) {
  const { loginWithRedirect } = useAuth0()

  return (
    <div className="gate-screen">
      <div className="gate-card">
        <h1 className="gate-wordmark">KATA</h1>
        {status === 'loading' && (
          <span className="gate-status" data-testid="sign-in-loading">
            Signing you in…
          </span>
        )}
        {status === 'error' && (
          <span className="gate-status gate-status--error" data-testid="sign-in-error">
            {message ?? 'Something went wrong signing you in.'}
          </span>
        )}
        {status !== 'loading' && (
          <>
            <p className="gate-blurb">Sign in to see your topics and take a rep.</p>
            <button data-testid="sign-in-button" onClick={() => loginWithRedirect()}>
              {status === 'error' ? 'Try again' : 'Sign in'}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
