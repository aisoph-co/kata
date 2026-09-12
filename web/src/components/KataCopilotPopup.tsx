import { CopilotKit, useCopilotAction } from '@copilotkit/react-core'
import { CopilotPopup } from '@copilotkit/react-ui'
import '@copilotkit/react-ui/styles.css'
import { useCopilotAuthHeaders } from '@/hooks/useCopilotAuthHeaders'
import { usePersona } from '@/lib/persona-store'
import { ChatMasteryChart, type ChatConceptMastery } from '@/components/copilot/ChatMasteryChart'
import { ChatTrendChart } from '@/components/copilot/ChatTrendChart'
import { ChatReviewCard, type ChatReviewItem } from '@/components/copilot/ChatReviewCard'
import type { HistoryReview } from '@/components/progress/ProgressChart'

const STARTER_SUGGESTIONS = [
  { title: 'How am I doing?', message: 'How am I doing?' },
  { title: 'Where am I weakest?', message: 'Where am I weakest?' },
  { title: 'Show my mastery by concept', message: 'Show my mastery by concept' },
  { title: 'What should I review?', message: 'What should I review?' },
]

/**
 * AE-25: the three insight-lane outcomes render here as CopilotKit
 * generative-UI actions. The runtime (`server/insight-adapter.ts`) decides
 * *whether* a turn needs one of these and supplies the exact data — the
 * arguments below always come from that server-authored payload, not from
 * anything a model generated, so a chart/card can never show a wrong
 * number. Must live inside `<CopilotKit>` for `useCopilotAction` to
 * register against the same conversation the popup renders.
 */
function KataCopilotChat({ runtimeUrl, headers }: { runtimeUrl: string; headers: Record<string, string> }) {
  useCopilotAction({
    name: 'showMasteryChart',
    description: "Render the signed-in person's mastery-by-concept chart",
    parameters: [{ name: 'concepts', type: 'object[]', required: true }],
    render: ({ args }) => <ChatMasteryChart concepts={(args?.concepts ?? []) as ChatConceptMastery[]} />,
  })

  useCopilotAction({
    name: 'showPKnownTrend',
    description: "Render the signed-in person's p_known trend for one concept",
    parameters: [
      { name: 'conceptId', type: 'string', required: true },
      { name: 'conceptTitle', type: 'string', required: false },
      { name: 'days', type: 'number', required: true },
      { name: 'reviews', type: 'object[]', required: true },
    ],
    render: ({ args }) => (
      <ChatTrendChart
        conceptId={(args?.conceptId ?? '') as string}
        days={(args?.days ?? 30) as number}
        reviews={(args?.reviews ?? []) as HistoryReview[]}
      />
    ),
  })

  useCopilotAction({
    name: 'showReviewCard',
    description: 'Render the next due review as an answerable card',
    parameters: [{ name: 'item', type: 'object', required: true }],
    render: ({ args }) =>
      args?.item ? <ChatReviewCard item={args.item as ChatReviewItem} runtimeUrl={runtimeUrl} headers={headers} /> : <></>,
  })

  return (
    <CopilotPopup
      labels={{
        title: 'Kata',
        initial: "Ask me anything you'd ask in a Kata DM.",
      }}
      suggestions={STARTER_SUGGESTIONS}
    />
  )
}

/**
 * W10/AE-25: the Kata bot in the web app. Mounted once at the router root
 * (`App.tsx`) so it is present on every screen behind the gate — one
 * popup, one look, one gate. An ordinary turn still forwards to the same
 * Hermes instance a Slack DM reaches; a turn about the person's own data,
 * a chart, or a review runs on OpenRouter instead — the routing lives
 * entirely server-side (`server/insight-adapter.ts`), never here. The
 * acting persona rides along as a hint only — the runtime resolves the
 * real identity from the verified ID token and ignores anything the
 * browser claims.
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
    <CopilotKit runtimeUrl={runtimeUrl} headers={headers} properties={{ actingPersona: persona.header }}>
      <KataCopilotChat runtimeUrl={runtimeUrl} headers={headers} />
    </CopilotKit>
  )
}
