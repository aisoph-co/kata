import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { navigate, useRoute } from './router'

describe('useRoute / navigate', () => {
  afterEach(() => {
    window.history.pushState({}, '', '/')
  })

  it('reads the current pathname', () => {
    window.history.pushState({}, '', '/dashboard')
    const { result } = renderHook(() => useRoute())
    expect(result.current).toBe('/dashboard')
  })

  it('navigate updates the path and every subscriber re-renders', () => {
    const { result } = renderHook(() => useRoute())
    act(() => navigate('/reps'))
    expect(result.current).toBe('/reps')
    expect(window.location.pathname).toBe('/reps')
  })

  it('is a no-op when already on the target path (no extra history entry)', () => {
    window.history.pushState({}, '', '/dashboard')
    const before = window.history.length
    act(() => navigate('/dashboard'))
    expect(window.history.length).toBe(before)
  })

  it('re-reads the path on a popstate event (browser back/forward)', () => {
    window.history.pushState({}, '', '/reps')
    const { result } = renderHook(() => useRoute())
    expect(result.current).toBe('/reps')

    // A real back/forward changes `location` and fires `popstate` itself;
    // simulated here as the two steps so the test doesn't depend on
    // jsdom's own history-stack timing.
    window.history.pushState({}, '', '/dashboard')
    act(() => window.dispatchEvent(new PopStateEvent('popstate')))
    expect(result.current).toBe('/dashboard')
  })
})
