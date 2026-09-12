import { CopilotKit } from '@copilotkit/react-core'
import { CopilotPopup } from '@copilotkit/react-ui'
import '@copilotkit/react-ui/styles.css'
import { useCopilotAuthHeaders } from '@/hooks/useCopilotAuthHeaders'
import { useWebSession } from '@/lib/session-store'

/**
 * W10: the Kata bot in the web app. Mounted once at the router root
 * (`App.tsx`) so it is present on every screen behind the gate — never a
 * second bot, never a second system prompt; every turn forwards to the same
 * Hermes instance the Slack DM uses (`web/server/index.ts`).
 *
 * Rendered only for a signed-in, role-confirmed session (W1) and unmounted
 * the moment that session clears (sign-out, or `useWebSession` going stale)
 * — `useWebSession` is a module-level store, so this reflects that instantly
 * with no prop threading. No generative UI, no frontend tools, no readable
 * screen state: default CopilotKit look, default behavior.
 */
export function KataCopilotPopup() {
  const session = useWebSession()
  const headers = useCopilotAuthHeaders(session)
  // Absolute — a client-only SPA has no same-origin `/api/copilotkit` to
  // relative-path against (CopilotKit's own docs); unset in a deployment
  // that hasn't reserved the runtime yet (D1), in which case the popup
  // stays off rather than pointing at nothing.
  const runtimeUrl = import.meta.env.VITE_COPILOTKIT_RUNTIME_URL as string | undefined

  // No session, no runtime configured, or (real Auth0 session) still
  // fetching the ID token the runtime needs to identify the caller — render
  // nothing rather than a popup that would just 401 on first message.
  if (!session || !runtimeUrl || !headers) return null

  return (
    <CopilotKit runtimeUrl={runtimeUrl} headers={headers}>
      <CopilotPopup
        labels={{
          title: 'Kata',
          initial: "Ask me anything you'd ask in a Kata DM.",
        }}
      />
    </CopilotKit>
  )
}
