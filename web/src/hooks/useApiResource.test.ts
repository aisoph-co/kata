import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { WebSession } from '@/lib/session-store'
import { useApiResource } from './useApiResource'

const SESSION: WebSession = {
  personId: 'p1',
  displayName: 'Hugo Marchetti',
  email: 'hugo.marchetti@ferry.example',
  isOperator: false,
  role: 'senior_swe',
  header: 'web:auth0|hugo',
}

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

describe('useApiResource', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('is a no-op while there is no live session', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useApiResource('/me/progress', null))

    expect(result.current).toMatchObject({ data: null, isPending: false, isError: false })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('fetches the path scoped to the session\'s X-Acting-Identity header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { concepts: [] }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useApiResource('/me/progress', SESSION))

    expect(result.current.isPending).toBe(true)
    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.data).toEqual({ concepts: [] })
    expect(fetchMock).toHaveBeenCalledWith('/api/me/progress', expect.objectContaining({ headers: expect.objectContaining({ 'X-Acting-Identity': SESSION.header }) }))
  })

  it('surfaces a failed request as isError, without throwing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(403, { detail: { code: 'unknown_identity', message: 'nope' } })))

    const { result } = renderHook(() => useApiResource('/me/progress', SESSION))

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.isError).toBe(true)
    expect(result.current.data).toBeNull()
  })

  it('refetch re-runs the same GET — the dashboard/reps live-update path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { concepts: [] }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useApiResource('/me/progress', SESSION))
    await waitFor(() => expect(result.current.isPending).toBe(false))

    act(() => result.current.refetch())
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })
})
