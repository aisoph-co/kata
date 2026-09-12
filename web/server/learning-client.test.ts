import assert from 'node:assert/strict'
import { describe, it, mock } from 'node:test'
import { LearningApiError, LearningClient } from './learning-client.ts'

function fakeResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

describe('LearningClient', () => {
  it('sends the trusted-caller shape (service bearer token + X-Acting-Identity)', async () => {
    const calls: { url: string; init: RequestInit }[] = []
    const fetchMock = mock.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init })
      return fakeResponse(200, { concepts: [], summary: { retention: {}, bypass_rate: null, calibration: null } })
    })
    const client = new LearningClient({ baseUrl: 'http://learning.example', serviceToken: 'svc-token' })
    // @ts-expect-error test double
    globalThis.fetch = fetchMock

    await client.getProgress('web:hugo@ferry.example')

    assert.equal(calls.length, 1)
    assert.equal(calls[0].url, 'http://learning.example/me/progress')
    const headers = calls[0].init.headers as Record<string, string>
    assert.equal(headers.Authorization, 'Bearer svc-token')
    assert.equal(headers['X-Acting-Identity'], 'web:hugo@ferry.example')
  })

  it('throws LearningApiError with the service`s code/message on a non-2xx response', async () => {
    // @ts-expect-error test double
    globalThis.fetch = mock.fn(async () => fakeResponse(403, { detail: { code: 'not_a_manager', message: 'acting person has no reports' } }))
    const client = new LearningClient({ baseUrl: 'http://learning.example', serviceToken: 'svc-token' })

    await assert.rejects(
      () => client.getTeamOverview('web:shane@ferry.example'),
      (error: unknown) => {
        assert.ok(error instanceof LearningApiError)
        assert.equal(error.status, 403)
        assert.equal(error.code, 'not_a_manager')
        return true
      },
    )
  })

  it('POSTs a review submission to /me/reviews with the body untouched', async () => {
    const calls: { url: string; init: RequestInit }[] = []
    // @ts-expect-error test double
    globalThis.fetch = mock.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init })
      return fakeResponse(200, { grade: 1, rating: 4, correct: true, explanation: null, confidence: null, bypassed: false, next_due_at: '2026-01-01T00:00:00Z', concept: { p_known: 0.9, mastered: true } })
    })
    const client = new LearningClient({ baseUrl: 'http://learning.example', serviceToken: 'svc-token' })

    const submission = { item_id: 'item-1', idempotency_key: 'key-1', response: { choice: 0 } }
    await client.submitReview('web:hugo@ferry.example', submission)

    assert.equal(calls[0].url, 'http://learning.example/me/reviews')
    assert.equal(calls[0].init.method, 'POST')
    assert.deepEqual(JSON.parse(calls[0].init.body as string), submission)
  })
})
