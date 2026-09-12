import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useTeamOverview } from './useTeamOverview'

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

describe('useTeamOverview', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches GET /team/overview with the acting identity header', async () => {
    const body = { concepts: [], people: [], retention: { d1: { accuracy: null, samples: 0 }, d7: { accuracy: null, samples: 0 }, d30: { accuracy: null, samples: 0 } } }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, body))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useTeamOverview('web:quinn'))

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.data).toEqual(body)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/team/overview',
      expect.objectContaining({ headers: expect.objectContaining({ 'X-Acting-Identity': 'web:quinn' }) }),
    )
  })

  it('surfaces a 403 not_a_manager as an error, not a thrown exception', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(403, { detail: { code: 'not_a_manager', message: 'no reports' } })),
    )

    const { result } = renderHook(() => useTeamOverview('web:hugo'))

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.isError).toBe(true)
    expect(result.current.data).toBeNull()
  })
})
