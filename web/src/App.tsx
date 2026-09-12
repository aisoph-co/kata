import { AppShell } from '@/components/AppShell'
import { Auth0ProviderWithNavigate } from '@/components/Auth0ProviderWithNavigate'
import { KataCopilotPopup } from '@/components/KataCopilotPopup'
import { SessionGate } from '@/components/SessionGate'
import { useRoute } from '@/lib/router'
import { Dashboard } from '@/pages/Dashboard'
import { Reps } from '@/pages/Reps'

/**
 * W1 built the sign-in + role-confirmation gate only. W2 is the learner's
 * own two screens behind it: the quiz-taking engine (`/reps`, flow 4b) and
 * the personal dashboard (`/dashboard`, frame 09). Topics/concept-map and
 * the manager team view (W3, W4) land in their own issues, on their own
 * routes, inside the same `AppShell`.
 */
function Screens() {
  const route = useRoute()
  return <AppShell>{route === '/dashboard' ? <Dashboard /> : <Reps />}</AppShell>
}

function App() {
  return (
    <Auth0ProviderWithNavigate>
      <SessionGate>
        <Screens />
      </SessionGate>
      {/* W10: reads the same module-level session store SessionGate
          populates, independent of which screen SessionGate is currently
          rendering — so it mounts once here, at the router root, rather
          than being threaded into every future screen (W2-W4). */}
      <KataCopilotPopup />
    </Auth0ProviderWithNavigate>
  )
}

export default App
