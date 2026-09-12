import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useTeamHeatmapMatrix } from './useTeamHeatmapMatrix'

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

describe('useTeamHeatmapMatrix', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('is idle with an empty matrix when there are no concepts', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useTeamHeatmapMatrix('web:quinn', []))

    expect(result.current).toEqual({ matrix: {}, isPending: false, isError: false, error: null })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('fetches one /team/concepts/{id} call per concept and assembles a person x concept matrix', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith('/team/concepts/c1')) {
        return Promise.resolve(
          jsonResponse(200, { concept_id: 'c1', people: [{ person_id: 'p1', p_known: 0.9, mastered: true }] }),
        )
      }
      return Promise.resolve(
        jsonResponse(200, { concept_id: 'c2', people: [{ person_id: 'p1', p_known: 0.1, mastered: false }] }),
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useTeamHeatmapMatrix('web:quinn', ['c1', 'c2']))

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.matrix).toEqual({
      p1: { c1: { p_known: 0.9, mastered: true }, c2: { p_known: 0.1, mastered: false } },
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('surfaces a failed concept fetch as isError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(403, { detail: { code: 'not_a_manager', message: 'no' } })))

    const { result } = renderHook(() => useTeamHeatmapMatrix('web:quinn', ['c1']))

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.isError).toBe(true)
    expect(result.current.matrix).toEqual({})
  })
})
