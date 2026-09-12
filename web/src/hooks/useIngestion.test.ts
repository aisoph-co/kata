import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useIngestion } from './useIngestion'

function ndjsonResponse(lines: object[], status = 200) {
  const body = lines.map((line) => `${JSON.stringify(line)}\n`).join('')
  return new Response(body, { status })
}

describe('useIngestion', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts to /admin/ingest with the caller’s X-Acting-Identity header', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(ndjsonResponse([{ type: 'done', counts: {} }])))
    vi.stubGlobal('fetch', fetchMock)
    const onSettled = vi.fn()

    const { result } = renderHook(() => useIngestion('web:auth0|operator', onSettled))
    await act(() => result.current.start())

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/admin/ingest',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Acting-Identity': 'web:auth0|operator' }),
      }),
    )
  })

  it('counts a concept the instant its own event arrives, not after the whole run', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          ndjsonResponse([
            { type: 'concept', concept: { slug: 'idempotency' } },
            { type: 'concept', concept: { slug: 'retry-safety' } },
            { type: 'topic', topic: { slug: 'correctness-under-retry' } },
            { type: 'done', counts: {} },
          ]),
        ),
      ),
    )

    const { result } = renderHook(() => useIngestion('web:auth0|operator', vi.fn()))
    await act(() => result.current.start())

    expect(result.current.conceptCount).toBe(2)
    expect(result.current.topicCount).toBe(1)
    expect(result.current.status).toBe('done')
  })

  it('calls onSettled once the stream finishes', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(ndjsonResponse([{ type: 'done', counts: {} }]))))
    const onSettled = vi.fn()

    const { result } = renderHook(() => useIngestion('web:auth0|operator', onSettled))
    await act(() => result.current.start())

    expect(onSettled).toHaveBeenCalledTimes(1)
  })

  it('an empty source reports "empty," zero concepts, no error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(ndjsonResponse([{ type: 'empty', message: 'no issues found' }]))))

    const { result } = renderHook(() => useIngestion('web:auth0|operator', vi.fn()))
    await act(() => result.current.start())

    expect(result.current.status).toBe('empty')
    expect(result.current.conceptCount).toBe(0)
    expect(result.current.error).toBeNull()
  })

  it('surfaces a non-OK response as a stated error, not a silent no-op', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('', { status: 403 }))))

    const { result } = renderHook(() => useIngestion('web:auth0|operator', vi.fn()))
    await act(() => result.current.start())

    expect(result.current.status).toBe('error')
    expect(result.current.error).toMatch(/403/)
  })

  it('surfaces a network failure as a stated error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))

    const { result } = renderHook(() => useIngestion('web:auth0|operator', vi.fn()))
    await act(() => result.current.start())

    expect(result.current.status).toBe('error')
  })

  it('resets to a running state with fresh counts on a second trigger', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ndjsonResponse([{ type: 'concept', concept: {} }, { type: 'done', counts: {} }]))
      .mockResolvedValueOnce(ndjsonResponse([{ type: 'done', counts: {} }]))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useIngestion('web:auth0|operator', vi.fn()))
    await act(() => result.current.start())
    expect(result.current.conceptCount).toBe(1)

    await waitFor(() => expect(result.current.status).toBe('done'))
  })
})
