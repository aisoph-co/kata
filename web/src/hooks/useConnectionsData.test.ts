import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useConnectionsData } from './useConnectionsData'

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

describe('useConnectionsData', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches /topics with all_roles=true, not the caller-own-role-filtered default', async () => {
    const fetchMock = vi.fn((path: string) => {
      if (path.startsWith('/api/topics')) return Promise.resolve(jsonResponse(200, { topics: [] }))
      return Promise.resolve(jsonResponse(200, { nodes: [], edges: [] }))
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useConnectionsData('web:auth0|hugo'))

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/topics?all_roles=true',
      expect.objectContaining({ headers: expect.objectContaining({ 'X-Acting-Identity': 'web:auth0|hugo' }) }),
    )
  })

  it('renders topics spanning more than one persona role on a single fetch', async () => {
    const topics = [
      { id: 't1', persona_role: 'junior_swe' },
      { id: 't2', persona_role: 'senior_swe' },
      { id: 't3', persona_role: 'pm' },
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn((path: string) =>
        Promise.resolve(
          path.startsWith('/api/topics') ? jsonResponse(200, { topics }) : jsonResponse(200, { nodes: [], edges: [] }),
        ),
      ),
    )

    const { result } = renderHook(() => useConnectionsData('web:auth0|hugo'))

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(new Set(result.current.topics.map((t) => t.persona_role))).toEqual(
      new Set(['junior_swe', 'senior_swe', 'pm']),
    )
  })

  it('surfaces a failed read as an error, not a silent empty result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))

    const { result } = renderHook(() => useConnectionsData('web:auth0|hugo'))

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.isError).toBe(true)
    expect(result.current.topics).toEqual([])
  })
})
