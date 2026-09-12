import { AppShell } from '@/components/AppShell'
import { Auth0ProviderWithNavigate } from '@/components/Auth0ProviderWithNavigate'
import { SessionGate } from '@/components/SessionGate'
import { useRoute } from '@/lib/router'
import { Connections } from '@/pages/Connections'
import { Dashboard } from '@/pages/Dashboard'
import { Reps } from '@/pages/Reps'

/**
 * W1 built the sign-in + role-confirmation gate only. W2 is the learner's
 * own two screens behind it: the quiz-taking engine (`/reps`, flow 4b) and
 * the personal dashboard (`/dashboard`, frame 09). W3 (this) adds
 * Connections (`/connections`, frame 02) — the team-context/concept-map
 * screen. The manager team view (W4) lands on its own route in its own
 * issue, inside the same `AppShell`.
 */
function Screens() {
  const route = useRoute()
  const screen = route === '/dashboard' ? <Dashboard /> : route === '/connections' ? <Connections /> : <Reps />
  return <AppShell>{screen}</AppShell>
}

function App() {
  return (
    <Auth0ProviderWithNavigate>
      <SessionGate>
        <Screens />
      </SessionGate>
    </Auth0ProviderWithNavigate>
  )
}

export default App
