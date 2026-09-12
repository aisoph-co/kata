import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useTeamPersonDetail } from './useTeamPersonDetail'

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

describe('useTeamPersonDetail', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('never fetches while personId is null', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useTeamPersonDetail('web:quinn', null))

    expect(result.current).toEqual({ data: null, isPending: false, isError: false, error: null })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('fetches GET /team/people/{id} once a personId is set', async () => {
    const body = {
      person_id: 'p1',
      concepts: [],
      adherence: 0.8,
      velocity: 2,
      due_count: 0,
      last_active: null,
      bypass_rate: null,
      retention: { d1: { accuracy: null, samples: 0 }, d7: { accuracy: null, samples: 0 }, d30: { accuracy: null, samples: 0 } },
      calibration: null,
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, body))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useTeamPersonDetail('web:quinn', 'p1'))

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.data).toEqual(body)
    expect(fetchMock).toHaveBeenCalledWith('/api/team/people/p1', expect.anything())
  })

  it('surfaces outside_subtree as an error, same as any other ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(403, { detail: { code: 'outside_subtree', message: 'not yours' } })),
    )

    const { result } = renderHook(() => useTeamPersonDetail('web:quinn', 'not-a-report'))

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.isError).toBe(true)
  })
})
