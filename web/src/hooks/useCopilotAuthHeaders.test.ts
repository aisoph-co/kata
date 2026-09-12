import { renderHook, waitFor } from '@testing-library/react'
import { useAuth0 } from '@auth0/auth0-react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { WebSession } from '@/lib/session-store'

vi.mock('@auth0/auth0-react', () => ({ useAuth0: vi.fn() }))

import { useCopilotAuthHeaders } from './useCopilotAuthHeaders'

const mockUseAuth0 = vi.mocked(useAuth0)

const SESSION: WebSession = {
  personId: 'p1',
  displayName: 'Hugo',
  email: 'hugo@ferry.example',
  isOperator: false,
  role: 'senior_swe',
  header: 'web:auth0|hugo',
}

function auth0State(overrides: Partial<ReturnType<typeof useAuth0>> = {}) {
  return {
    isAuthenticated: false,
    getIdTokenClaims: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as ReturnType<typeof useAuth0>
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('useCopilotAuthHeaders (AUTH_ENABLED = true)', () => {
  vi.mock('@/lib/auth-config', () => ({ AUTH_ENABLED: true }))

  it('returns undefined with no session — nothing to gate the popup on', () => {
    mockUseAuth0.mockReturnValue(auth0State())
    const { result } = renderHook(() => useCopilotAuthHeaders(null))
    expect(result.current).toBeUndefined()
  })

  it('returns {} for a session with no Auth0 sign-in (the e2e bypass path) — its own headers travel separately', () => {
    mockUseAuth0.mockReturnValue(auth0State({ isAuthenticated: false }))
    const { result } = renderHook(() => useCopilotAuthHeaders(SESSION))
    expect(result.current).toEqual({})
  })

  it('returns undefined while the ID token is still in flight, then the bearer header once resolved', async () => {
    const getIdTokenClaims = vi.fn().mockResolvedValue({ __raw: 'signed.jwt.token' })
    mockUseAuth0.mockReturnValue(auth0State({ isAuthenticated: true, getIdTokenClaims }))

    const { result } = renderHook(() => useCopilotAuthHeaders(SESSION))
    expect(result.current).toBeUndefined()

    await waitFor(() => expect(result.current).toEqual({ Authorization: 'Bearer signed.jwt.token' }))
  })

  it('falls back to undefined if Auth0 fails to produce a token — never sends a request with no credential', async () => {
    const getIdTokenClaims = vi.fn().mockRejectedValue(new Error('network'))
    mockUseAuth0.mockReturnValue(auth0State({ isAuthenticated: true, getIdTokenClaims }))

    const { result, rerender } = renderHook(() => useCopilotAuthHeaders(SESSION))
    rerender()
    await waitFor(() => expect(getIdTokenClaims).toHaveBeenCalled())
    expect(result.current).toBeUndefined()
  })
})
