import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiFetch, ApiError } from './api-client'

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('apiFetch', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends X-Acting-Identity and the JSON body, and returns the parsed JSON on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { id: 'p1' }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await apiFetch('/identities/resolve', {
      persona: { header: 'web:auth0|abc' },
      method: 'POST',
      body: { platform: 'web', external_id: 'a@example.com' },
    })

    expect(result).toEqual({ id: 'p1' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/identities/resolve',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Acting-Identity': 'web:auth0|abc' }),
        body: JSON.stringify({ platform: 'web', external_id: 'a@example.com' }),
      }),
    )
  })

  it('throws an ApiError carrying the core error code on a non-2xx response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(403, { detail: { code: 'unknown_identity', message: 'nope' } })),
    )

    await expect(apiFetch('/identities/resolve', { method: 'POST', body: {} })).rejects.toMatchObject({
      status: 403,
      code: 'unknown_identity',
      message: 'nope',
    })
  })

  it('throws a network_error ApiError with status 0 when fetch itself rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))

    const error = await apiFetch('/health').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(0)
    expect((error as ApiError).code).toBe('network_error')
  })
})
