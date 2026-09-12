import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useAuth0 } from '@auth0/auth0-react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useE2ESession } from '@/hooks/useE2ESession'
import { useSessionResolve } from '@/hooks/useSessionResolve'
import { ApiError } from '@/lib/api-client'
import { resetRoleConfirm } from '@/lib/role-confirm-store'
import { clearWebSession, useWebSession, type WebSession } from '@/lib/session-store'

vi.mock('@/lib/auth-config', () => ({ AUTH_ENABLED: true }))
vi.mock('@auth0/auth0-react', () => ({ useAuth0: vi.fn() }))
vi.mock('@/hooks/useE2ESession', () => ({ useE2ESession: vi.fn() }))
vi.mock('@/hooks/useSessionResolve', () => ({ useSessionResolve: vi.fn() }))

import { SessionGate } from './SessionGate'

const mockUseAuth0 = vi.mocked(useAuth0)
const mockUseE2ESession = vi.mocked(useE2ESession)
const mockUseSessionResolve = vi.mocked(useSessionResolve)

const HUGO = { id: 'p1', display_name: 'Hugo Marchetti', email: 'hugo.marchetti@ferry.example', is_operator: false, role: 'senior_swe' as string | null }

function signedOutAuth0() {
  return { isLoading: false, isAuthenticated: false, error: undefined, user: undefined, loginWithRedirect: vi.fn(), logout: vi.fn() } as any
}

function renderGate() {
  return render(
    <SessionGate>
      <div data-testid="app-child">app</div>
    </SessionGate>,
  )
}

/** Surfaces `useWebSession()` as text so a test can assert on it directly. */
function SessionProbe() {
  const session: WebSession | null = useWebSession()
  return <div data-testid="app-child">{session ? `${session.personId}:${session.role}` : 'no session'}</div>
}

describe('SessionGate (AUTH_ENABLED = true)', () => {
  beforeEach(() => {
    resetRoleConfirm()
    clearWebSession()
    mockUseAuth0.mockReturnValue(signedOutAuth0())
    mockUseE2ESession.mockReturnValue({ data: null, isPending: false })
    mockUseSessionResolve.mockReturnValue({ data: null, isPending: false, isError: false, error: null })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('shows the loading state while the e2e-bypass check is in flight', () => {
    mockUseE2ESession.mockReturnValue({ data: null, isPending: true })

    renderGate()

    expect(screen.getByTestId('sign-in-loading')).toBeInTheDocument()
  })

  it('shows the sign-in button when signed out and not bypassed', () => {
    renderGate()

    expect(screen.getByTestId('sign-in-button')).toBeInTheDocument()
  })

  it('shows a fixed refusal screen when the resolve call comes back 403, and never renders the app', () => {
    mockUseAuth0.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      error: undefined,
      user: { email_verified: true, email: 'nobody@example.com', sub: 'auth0|zzz' },
      loginWithRedirect: vi.fn(),
      logout: vi.fn(),
    } as any)
    mockUseSessionResolve.mockReturnValue({
      data: null,
      isPending: false,
      isError: true,
      error: new ApiError(403, 'unknown_identity', 'no match'),
    })

    renderGate()

    expect(screen.getByTestId('sign-in-refused')).toBeInTheDocument()
    expect(screen.queryByTestId('app-child')).not.toBeInTheDocument()
  })

  it('blocks on RoleRequired when the resolved person has no role, with an explicit prompt', () => {
    mockUseAuth0.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      error: undefined,
      user: { email_verified: true, email: HUGO.email, sub: 'auth0|hugo' },
      loginWithRedirect: vi.fn(),
      logout: vi.fn(),
    } as any)
    mockUseSessionResolve.mockReturnValue({ data: { ...HUGO, role: null }, isPending: false, isError: false, error: null })

    renderGate()

    expect(screen.getByTestId('role-required')).toBeInTheDocument()
    expect(screen.queryByTestId('app-child')).not.toBeInTheDocument()
  })

  it('shows role-confirm pre-filled with the seeded role, and one click on Confirm renders the app', () => {
    mockUseAuth0.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      error: undefined,
      user: { email_verified: true, email: HUGO.email, sub: 'auth0|hugo' },
      loginWithRedirect: vi.fn(),
      logout: vi.fn(),
    } as any)
    mockUseSessionResolve.mockReturnValue({ data: HUGO, isPending: false, isError: false, error: null })

    renderGate()

    expect(screen.getByTestId('role-confirm')).toBeInTheDocument()
    expect(screen.getByTestId('role-confirm-current')).toHaveTextContent('Senior SWE')

    fireEvent.click(screen.getByTestId('role-confirm-accept'))

    expect(screen.getByTestId('app-child')).toBeInTheDocument()
  })

  it('records the confirmed session for downstream screens to read via useWebSession', () => {
    mockUseAuth0.mockReturnValue({
      isLoading: false,
      isAuthenticated: true,
      error: undefined,
      user: { email_verified: true, email: HUGO.email, sub: 'auth0|hugo' },
      loginWithRedirect: vi.fn(),
      logout: vi.fn(),
    } as any)
    mockUseSessionResolve.mockReturnValue({ data: HUGO, isPending: false, isError: false, error: null })

    render(
      <SessionGate>
        <SessionProbe />
      </SessionGate>,
    )

    fireEvent.click(screen.getByTestId('role-confirm-accept'))

    expect(screen.getByTestId('app-child')).toHaveTextContent(`${HUGO.id}:${HUGO.role}`)
  })

  it('e2e bypass: resolves the named learner and takes the role as confirmed, skipping role-confirm entirely', () => {
    mockUseE2ESession.mockReturnValue({ data: { email: HUGO.email }, isPending: false })
    mockUseSessionResolve.mockReturnValue({ data: HUGO, isPending: false, isError: false, error: null })

    renderGate()

    expect(screen.queryByTestId('role-confirm')).not.toBeInTheDocument()
    expect(screen.queryByTestId('sign-in-button')).not.toBeInTheDocument()
    expect(screen.getByTestId('app-child')).toBeInTheDocument()
  })

  it('e2e bypass: an unknown seed email still gets the fixed refusal screen, not a free pass', () => {
    mockUseE2ESession.mockReturnValue({ data: { email: 'nobody@ferry.example' }, isPending: false })
    mockUseSessionResolve.mockReturnValue({
      data: null,
      isPending: false,
      isError: true,
      error: new ApiError(403, 'unknown_identity', 'no match'),
    })

    renderGate()

    expect(screen.getByTestId('sign-in-refused')).toBeInTheDocument()
  })
})
