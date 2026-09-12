import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useApiResource } from '@/hooks/useApiResource'
import type { NextItemsResponse } from '@/lib/quiz-types'
import { useWebSession, type WebSession } from '@/lib/session-store'
import { Reps } from './Reps'

vi.mock('@/hooks/useApiResource', () => ({ useApiResource: vi.fn() }))
vi.mock('@/lib/session-store', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/session-store')>()),
  useWebSession: vi.fn(),
}))

const mockUseApiResource = vi.mocked(useApiResource)
const mockUseWebSession = vi.mocked(useWebSession)

const SESSION: WebSession = {
  personId: 'p1',
  displayName: 'Hugo Marchetti',
  email: 'hugo.marchetti@ferry.example',
  isOperator: false,
  role: 'senior_swe',
  header: 'web:auth0|hugo',
}

function resource(data: NextItemsResponse | null, overrides: Partial<ReturnType<typeof useApiResource>> = {}) {
  return { data, isPending: false, isError: false, error: null, refetch: vi.fn(), ...overrides }
}

describe('Reps', () => {
  it('renders the first due item from GET /me/next', () => {
    mockUseWebSession.mockReturnValue(SESSION)
    mockUseApiResource.mockReturnValue(
      resource({
        items: [{ id: 'i1', concept_id: 'c1', kind: 'mcq', prompt: 'Pick one', payload: { options: ['a', 'b'] } }],
      }),
    )

    render(<Reps />)

    expect(screen.getByTestId('quiz-item-card')).toHaveAttribute('data-item-id', 'i1')
    expect(screen.getByTestId('reps-position')).toHaveTextContent('1 of 1')
  })

  it('failure path A: an empty queue renders the served reason, not a blank state', () => {
    mockUseWebSession.mockReturnValue(SESSION)
    mockUseApiResource.mockReturnValue(resource({ items: [], reason: 'blocked_by_prerequisites' }))

    render(<Reps />)

    const empty = screen.getByTestId('reps-empty')
    expect(empty).toHaveAttribute('data-reason', 'blocked_by_prerequisites')
    expect(empty).toHaveTextContent(/prerequisite/i)
  })

  it('an unrecognised reason still shows a real message rather than an invented one matching no enum value', () => {
    mockUseWebSession.mockReturnValue(SESSION)
    mockUseApiResource.mockReturnValue(resource({ items: [] }))

    render(<Reps />)

    expect(screen.getByTestId('reps-empty')).toHaveTextContent('Nothing is due right now.')
  })
})
