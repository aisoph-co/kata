import { Auth0ProviderWithNavigate } from '@/components/Auth0ProviderWithNavigate'
import { SessionGate } from '@/components/SessionGate'

/**
 * W1 is the sign-in + role-confirmation gate only — the screens behind it
 * (topics/concept-map, quiz-taking, dashboard, team view: W2-W4) land in
 * their own issues. This placeholder is what a signed-in, role-confirmed
 * session renders today; `persona-menu-trigger` is the app-shell marker
 * `build-day/tests/e2e` looks for to know the gate has been passed.
 */
function SignedInPlaceholder() {
  return (
    <div className="gate-screen">
      <div className="gate-card" data-testid="persona-menu-trigger">
        <h1 className="gate-wordmark">KATA</h1>
        <p className="gate-blurb">Signed in — the rest of the app is on its way.</p>
      </div>
    </div>
  )
}

function App() {
  return (
    <Auth0ProviderWithNavigate>
      <SessionGate>
        <SignedInPlaceholder />
      </SessionGate>
    </Auth0ProviderWithNavigate>
  )
}

export default App
