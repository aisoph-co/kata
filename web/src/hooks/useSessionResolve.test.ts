import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useSessionResolve } from './useSessionResolve'

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

describe('useSessionResolve', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('is a no-op while identity is null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useSessionResolve(null))

    expect(result.current).toEqual({ data: null, isPending: false, isError: false, error: null })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('resolves against POST /identities/resolve with the normalized email and X-Acting-Identity', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { id: 'p1', display_name: 'Hugo Marchetti', email: 'hugo@ferry.example', is_operator: false, role: 'senior_swe' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useSessionResolve({ subject: 'auth0|abc', email: '  Hugo@Ferry.example ' }))

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.data?.id).toBe('p1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/identities/resolve',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Acting-Identity': 'web:auth0|abc' }),
        body: JSON.stringify({ platform: 'web', external_id: 'hugo@ferry.example' }),
      }),
    )
  })

  it('surfaces an unknown identity as an ApiError with status 403, no retry', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(403, { detail: { code: 'unknown_identity', message: 'no match' } })))

    const { result } = renderHook(() => useSessionResolve({ subject: 'auth0|zzz', email: 'nobody@example.com' }))

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.isError).toBe(true)
    expect(result.current.data).toBeNull()
  })
})
