/**
 * AE-25: the routing `CopilotServiceAdapter` behind the one `/copilotkit`
 * endpoint — the person never picks a lane and never sees a seam.
 *
 * Every turn is classified deterministically (`insight-router.ts`) before
 * either model is touched:
 *  - No match -> forwarded to the real Hermes adapter, `actions` stripped
 *    so Hermes's request looks exactly like it did before this feature
 *    existed (same shared thread as the Slack DM either way).
 *  - A match -> handled entirely here: fetch the person's real data,
 *    phrase it with OpenRouter, and (for a chart/review-card intent) emit
 *    the matching frontend action with the fetched data as its arguments.
 *    Hermes is never called for these turns.
 */
import { randomUUID } from 'node:crypto'
import type { CopilotRuntimeChatCompletionRequest, CopilotRuntimeChatCompletionResponse, CopilotServiceAdapter } from '@copilotkit/runtime'
import { classifyIntent } from './insight-router.js'
import { buildInsightReply, type OpenRouterConfig } from './insight-data.js'
import type { LearningClient } from './learning-client.js'

export interface RoutingAdapterParams {
  hermesAdapter: CopilotServiceAdapter
  learningClient: LearningClient
  actingIdentity: string
  openRouter: OpenRouterConfig | null
}

function lastUserMessageText(request: CopilotRuntimeChatCompletionRequest): string | null {
  for (let i = request.messages.length - 1; i >= 0; i--) {
    const message = request.messages[i]
    if (message.isTextMessage() && message.role === 'user') return message.content
  }
  return null
}

export class RoutingServiceAdapter implements CopilotServiceAdapter {
  provider = 'kata-insight-router'

  constructor(private readonly params: RoutingAdapterParams) {}

  async process(request: CopilotRuntimeChatCompletionRequest): Promise<CopilotRuntimeChatCompletionResponse> {
    const userText = lastUserMessageText(request)
    const intent = userText ? classifyIntent(userText) : null

    if (!intent || !userText) {
      // Plain conversation: Hermes, unchanged. `actions` didn't exist on
      // these requests before AE-25 registered any — stripping them keeps
      // Hermes's payload identical to what it always saw.
      return this.params.hermesAdapter.process({ ...request, actions: [] })
    }

    const threadId = request.threadId ?? randomUUID()
    const runId = randomUUID()
    const { learningClient, actingIdentity, openRouter } = this.params

    request.eventSource.stream(async (eventStream$) => {
      const reply = await buildInsightReply(intent, { learningClient, actingIdentity, openRouter, userText })

      const messageId = randomUUID()
      eventStream$.sendTextMessage(messageId, reply.text)

      if (reply.action) {
        const actionExecutionId = randomUUID()
        eventStream$.sendActionExecutionStart({ actionExecutionId, actionName: reply.action.name, parentMessageId: messageId })
        eventStream$.sendActionExecutionArgs({ actionExecutionId, args: JSON.stringify(reply.action.args) })
        eventStream$.sendActionExecutionEnd({ actionExecutionId })
      }

      eventStream$.complete()
    })

    return { threadId, runId }
  }
}
