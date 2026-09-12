import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/auth-config', () => ({ AUTH_ENABLED: true }))

import { useE2ESession } from './useE2ESession'

describe('useE2ESession', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('resolves the granted email on a 200 from /__e2e/session', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ email: 'hugo.marchetti@ferry.example' }), { status: 200 })),
    )

    const { result } = renderHook(() => useE2ESession())

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.data).toEqual({ email: 'hugo.marchetti@ferry.example' })
  })

  it('resolves null (no bypass) on a 404', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 404 })))

    const { result } = renderHook(() => useE2ESession())

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.data).toBeNull()
  })

  it('resolves null when the request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))

    const { result } = renderHook(() => useE2ESession())

    await waitFor(() => expect(result.current.isPending).toBe(false))
    expect(result.current.data).toBeNull()
  })
})
