import { CopilotKit } from '@copilotkit/react-core'
import { CopilotPopup } from '@copilotkit/react-ui'
import '@copilotkit/react-ui/styles.css'
import { useCopilotAuthHeaders } from '@/hooks/useCopilotAuthHeaders'
import { usePersona } from '@/lib/persona-store'

/**
 * W10: the Kata bot in the web app. Mounted once at the router root
 * (`App.tsx`) so it is present on every screen behind the gate — never a
 * second bot, never a second system prompt; every turn forwards to the same
 * Hermes instance a Slack DM reaches (`server/index.ts`).
 *
 * No generative UI, no frontend tools, no readable screen state: default
 * CopilotKit look, default behaviour. The acting persona rides along as a
 * hint only — the runtime resolves the real identity from the verified ID
 * token and ignores anything the browser claims.
 */
export function KataCopilotPopup() {
  const persona = usePersona()
  const headers = useCopilotAuthHeaders()
  // Absolute: a client-only SPA has no same-origin `/api/copilotkit` to
  // relative-path against. Unset in a deployment that hasn't provisioned
  // the runtime, in which case the popup stays off rather than pointing at
  // nothing.
  const runtimeUrl = import.meta.env.VITE_COPILOTKIT_RUNTIME_URL as string | undefined

  // No runtime configured, or (real Auth0 session) still fetching the ID
  // token the runtime needs — render nothing rather than a popup that would
  // 401 on its first message.
  if (!runtimeUrl || !headers) return null

  return (
    <CopilotKit
      runtimeUrl={runtimeUrl}
      headers={headers}
      properties={{ actingPersona: persona.header }}
    >
      <CopilotPopup
        labels={{
          title: 'Kata',
          initial: "Ask me anything you'd ask in a Kata DM.",
        }}
      />
    </CopilotKit>
  )
}
