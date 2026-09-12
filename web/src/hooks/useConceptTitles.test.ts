import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useConceptTitles } from './useConceptTitles'

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

describe('useConceptTitles', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('maps concept_id to title/slug from GET /me/concept-graph', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(200, {
          nodes: [{ concept_id: 'c1', slug: 'idempotency', title: 'Idempotency', p_known: 0.2, mastered: false, unlocked: true }],
          edges: [],
        }),
      ),
    )

    const { result } = renderHook(() => useConceptTitles('web:quinn'))

    await waitFor(() => expect(result.current.c1).toEqual({ slug: 'idempotency', title: 'Idempotency' }))
  })

  it('leaves titles empty on failure rather than throwing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('down')))

    const { result } = renderHook(() => useConceptTitles('web:quinn'))

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(result.current).toEqual({})
  })
})
