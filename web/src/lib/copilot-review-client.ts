/**
 * AE-25: the chat review card's Submit/Bypass call this — the runtime's own
 * `POST /copilotkit/review`, never `/api/*` (that path acts as whichever
 * demo persona is selected; the chat card must act as the server-resolved
 * signed-in person, same identity the popup itself already authenticates
 * with — see `useCopilotAuthHeaders`).
 */
import type { ReviewResult } from '@/components/copilot/ChatReviewCard'

export class CopilotReviewError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'CopilotReviewError'
    this.status = status
  }
}

/** `.../copilotkit` -> `.../copilotkit/review`. */
function reviewEndpoint(runtimeUrl: string): string {
  return runtimeUrl.replace(/\/copilotkit\/?$/, '/copilotkit/review')
}

export async function submitCopilotReview(
  runtimeUrl: string,
  headers: Record<string, string>,
  body: {
    item_id: string
    idempotency_key: string
    response: Record<string, unknown>
    bypassed?: boolean
    confidence?: number | null
  },
): Promise<ReviewResult> {
  const res = await fetch(reviewEndpoint(runtimeUrl), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  })
  const text = await res.text()
  const json = text ? JSON.parse(text) : null
  if (!res.ok) {
    throw new CopilotReviewError(res.status, json?.message ?? json?.error ?? res.statusText)
  }
  return json as ReviewResult
}
