import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useE2ESession } from '@/hooks/useE2ESession'
import { useSessionResolve } from '@/hooks/useSessionResolve'
import { ApiError } from '@/lib/api-client'
import { clearWebSession } from '@/lib/session-store'
import { resetRoleConfirm } from '@/lib/role-confirm-store'

vi.mock('@/lib/auth-config', () => ({ AUTH_ENABLED: false }))
vi.mock('@auth0/auth0-react', () => ({
  // Never expected to be called on this path — a real call (no Auth0Provider
  // mounted) would throw, which is exactly the regression guard we want.
  useAuth0: vi.fn(() => {
    throw new Error('useAuth0 must not be called when AUTH_ENABLED is false')
  }),
}))
vi.mock('@/hooks/useE2ESession', () => ({ useE2ESession: vi.fn() }))
vi.mock('@/hooks/useSessionResolve', () => ({ useSessionResolve: vi.fn() }))

import { SessionGate } from './SessionGate'

const mockUseE2ESession = vi.mocked(useE2ESession)
const mockUseSessionResolve = vi.mocked(useSessionResolve)

// No Auth0 tenant configured in this workspace yet. Regression coverage for
// the reviewed finding: this must never be a silent passthrough, and the
// e2e bypass must still be able to mint a session with no tenant at all.
describe('SessionGate (AUTH_ENABLED = false, no Auth0 tenant configured)', () => {
  beforeEach(() => {
    resetRoleConfirm()
    clearWebSession()
  })

  it('blocks with a fixed unavailable screen when there is no e2e bypass either — never a silent passthrough', () => {
    mockUseE2ESession.mockReturnValue({ data: null, isPending: false })
    mockUseSessionResolve.mockReturnValue({ data: null, isPending: false, isError: false, error: null })

    render(
      <SessionGate>
        <div data-testid="app-child">app</div>
      </SessionGate>,
    )

    expect(screen.getByTestId('sign-in-unavailable')).toBeInTheDocument()
    expect(screen.queryByTestId('app-child')).not.toBeInTheDocument()
  })

  it('the e2e bypass still resolves a session with no Auth0 tenant configured at all', () => {
    mockUseE2ESession.mockReturnValue({ data: { email: 'hugo.marchetti@ferry.example' }, isPending: false })
    mockUseSessionResolve.mockReturnValue({
      data: {
        id: 'p1',
        display_name: 'Hugo Marchetti',
        email: 'hugo.marchetti@ferry.example',
        is_operator: false,
        role: 'senior_swe',
      },
      isPending: false,
      isError: false,
      error: null,
    })

    render(
      <SessionGate>
        <div data-testid="app-child">app</div>
      </SessionGate>,
    )

    expect(screen.getByTestId('app-child')).toBeInTheDocument()
    expect(screen.queryByTestId('sign-in-unavailable')).not.toBeInTheDocument()
    expect(screen.queryByTestId('role-confirm')).not.toBeInTheDocument()
  })

  it('the e2e bypass still refuses an unknown seed identity with no tenant configured', () => {
    mockUseE2ESession.mockReturnValue({ data: { email: 'nobody@ferry.example' }, isPending: false })
    mockUseSessionResolve.mockReturnValue({
      data: null,
      isPending: false,
      isError: true,
      error: new ApiError(403, 'unknown_identity', 'no match'),
    })

    render(
      <SessionGate>
        <div data-testid="app-child">app</div>
      </SessionGate>,
    )

    expect(screen.getByTestId('sign-in-refused')).toBeInTheDocument()
    expect(screen.queryByTestId('app-child')).not.toBeInTheDocument()
  })
})
