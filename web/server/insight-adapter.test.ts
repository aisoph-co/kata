/**
 * AE-25: the routing decision itself — the part of this feature with no
 * live service to smoke-test against (Hermes/OpenRouter/learning service
 * are all real network calls). Everything here is a fake: a fake
 * `eventSource` records what the adapter emits, a fake `hermesAdapter`
 * records the request it was handed, and a fake `LearningClient` returns
 * canned data or throws `LearningApiError` the way the real one would on a
 * 403. `node --test` (this repo's own convention — `identity.test.ts`),
 * not vitest: no DOM, no bundler needed for plain functions + a fake.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { RoutingServiceAdapter } from './insight-adapter.ts'
import { LearningApiError } from './learning-client.ts'
import type { CopilotRuntimeChatCompletionRequest } from '@copilotkit/runtime'

function textMessage(role: 'user' | 'assistant', content: string) {
  return { role, content, isTextMessage: () => true, isActionExecutionMessage: () => false }
}

function fakeEventSource() {
  const events: Record<string, unknown>[] = []
  const eventStream$ = {
    sendTextMessage: (messageId: string, content: string) => events.push({ type: 'text', messageId, content }),
    sendActionExecutionStart: (p: object) => events.push({ type: 'actionStart', ...p }),
    sendActionExecutionArgs: (p: object) => events.push({ type: 'actionArgs', ...p }),
    sendActionExecutionEnd: (p: object) => events.push({ type: 'actionEnd', ...p }),
    complete: () => events.push({ type: 'complete' }),
  }
  let ran: Promise<unknown> = Promise.resolve()
  return {
    events,
    eventSource: {
      stream: (callback: (s: typeof eventStream$) => Promise<void>) => {
        ran = callback(eventStream$)
      },
    },
    settle: () => ran,
  }
}

function baseRequest(userText: string, eventSource: unknown): CopilotRuntimeChatCompletionRequest {
  return {
    eventSource,
    messages: [textMessage('user', userText)],
    actions: [{ name: 'showMasteryChart', description: '', jsonSchema: '{}' }],
    threadId: 'thread-1',
  } as unknown as CopilotRuntimeChatCompletionRequest
}

describe('RoutingServiceAdapter', () => {
  it('forwards a plain conversational turn to Hermes with actions stripped', async () => {
    const { eventSource } = fakeEventSource()
    let seenRequest: CopilotRuntimeChatCompletionRequest | undefined
    const hermesAdapter = {
      process: async (request: CopilotRuntimeChatCompletionRequest) => {
        seenRequest = request
        return { threadId: 'thread-1' }
      },
    }
    const adapter = new RoutingServiceAdapter({
      hermesAdapter,
      learningClient: {} as never,
      actingIdentity: 'web:hugo@ferry.example',
      openRouter: null,
    })

    await adapter.process(baseRequest('thanks, that helps a lot', eventSource))

    assert.ok(seenRequest)
    assert.deepEqual(seenRequest!.actions, [])
  })

  it('answers a data question from the insight lane without ever calling Hermes', async () => {
    const { eventSource, events, settle } = fakeEventSource()
    const hermesAdapter = { process: async () => { throw new Error('Hermes must not be called for a data turn') } }
    const learningClient = {
      getProgress: async () => ({
        concepts: [{ concept_id: 'c1', p_known: 0.9, mastered: true, due_count: 0, unlocked: true }],
        summary: { retention: { d1: { accuracy: 1, samples: 5 }, d7: { accuracy: 0.8, samples: 6 }, d30: { accuracy: null, samples: 1 } }, bypass_rate: 0.1, calibration: 0.02 },
      }),
    }
    const adapter = new RoutingServiceAdapter({
      hermesAdapter,
      learningClient: learningClient as never,
      actingIdentity: 'web:hugo@ferry.example',
      openRouter: null,
    })

    await adapter.process(baseRequest('how am I doing?', eventSource))
    await settle()

    const textEvent = events.find((e) => e.type === 'text')
    assert.ok(textEvent, 'expected a text reply')
    assert.match(String(textEvent!.content), /80%/) // 7-day retention, from the fake data above
    assert.equal(events.some((e) => e.type === 'actionStart'), false, 'a plain numbers answer needs no chart/card')
  })

  it('emits the mastery chart action with the real fetched numbers as args', async () => {
    const { eventSource, events, settle } = fakeEventSource()
    const hermesAdapter = { process: async () => ({ threadId: 't' }) }
    const learningClient = {
      getProgress: async () => ({
        concepts: [{ concept_id: 'c1', p_known: 0.42, mastered: false, due_count: 2, unlocked: true }],
        summary: { retention: {}, bypass_rate: null, calibration: null },
      }),
    }
    const adapter = new RoutingServiceAdapter({
      hermesAdapter,
      learningClient: learningClient as never,
      actingIdentity: 'web:hugo@ferry.example',
      openRouter: null,
    })

    await adapter.process(baseRequest('show my mastery by concept', eventSource))
    await settle()

    const argsEvent = events.find((e) => e.type === 'actionArgs') as { args: string } | undefined
    assert.ok(argsEvent, 'expected an action args event')
    const parsed = JSON.parse(argsEvent!.args)
    assert.deepEqual(parsed.concepts, [{ concept_id: 'c1', p_known: 0.42, unlocked: true }])
    assert.equal(events.find((e) => e.type === 'actionStart')?.actionName, 'showMasteryChart')
  })

  it('refuses a team question with no figures when the learning service says not_a_manager', async () => {
    const { eventSource, events, settle } = fakeEventSource()
    const hermesAdapter = { process: async () => ({ threadId: 't' }) }
    const learningClient = {
      getTeamOverview: async () => {
        throw new LearningApiError(403, 'not_a_manager', 'acting person has no reports')
      },
    }
    const adapter = new RoutingServiceAdapter({
      hermesAdapter,
      learningClient: learningClient as never,
      actingIdentity: 'web:shane@ferry.example',
      openRouter: null,
    })

    await adapter.process(baseRequest('how is my team doing?', eventSource))
    await settle()

    const textEvent = events.find((e) => e.type === 'text')
    const content = String(textEvent?.content ?? '')
    assert.match(content, /only show you your own numbers/i)
    assert.doesNotMatch(content, /\d/) // no figures leaked into the refusal
  })
})
