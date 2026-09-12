import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useTeamAudit } from './useTeamAudit'

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

describe('useTeamAudit', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches GET /team/audit and refetches when refreshKey changes', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { entries: [] }))
      .mockResolvedValueOnce(
        jsonResponse(200, {
          entries: [{ id: 'a1', actor_person_id: 'quinn', subject_scope: 'hugo', endpoint: '/team/people/hugo', at: '2026-09-12T00:00:00Z' }],
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const { result, rerender } = renderHook(({ key }: { key: number }) => useTeamAudit('web:quinn', key), {
      initialProps: { key: 0 },
    })

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.data?.entries).toEqual([])

    rerender({ key: 1 })

    await waitFor(() => expect(result.current.data?.entries).toHaveLength(1))
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
