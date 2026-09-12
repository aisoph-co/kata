import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useApiResource } from '@/hooks/useApiResource'
import type { ConceptGraphResponse, ProgressResponse } from '@/lib/quiz-types'
import { useWebSession, type WebSession } from '@/lib/session-store'
import { Dashboard } from './Dashboard'

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

const PROGRESS: ProgressResponse = {
  concepts: [
    { concept_id: 'c1', p_known: 0.93, mastered: true, due_count: 0, unlocked: true },
    { concept_id: 'c2', p_known: 0.2, mastered: false, due_count: 1, unlocked: false },
  ],
  summary: {
    retention: { d1: { accuracy: 1, samples: 40 }, d7: { accuracy: 0.91, samples: 40 }, d30: { accuracy: 0.67, samples: 40 } },
    bypass_rate: 0.057,
    calibration: 0.02,
    review_count: 494,
    last_active: new Date().toISOString(),
  },
}

const GRAPH: ConceptGraphResponse = {
  nodes: [
    { concept_id: 'c1', slug: 'idempotency', title: 'Idempotency keys', p_known: 0.93, mastered: true, unlocked: true },
    { concept_id: 'c2', slug: 'sca-exemptions', title: 'SCA and exemptions', p_known: 0.2, mastered: false, unlocked: false },
  ],
  edges: [],
}

function resource<T>(data: T | null, overrides: Partial<ReturnType<typeof useApiResource>> = {}) {
  return { data, isPending: false, isError: false, error: null, refetch: vi.fn(), ...overrides }
}

describe('Dashboard', () => {
  it('renders the four MVP tiles, the delta on the bypass tile, the mastery table, and the footer', () => {
    mockUseWebSession.mockReturnValue(SESSION)
    mockUseApiResource.mockImplementation((path) => (path === '/me/progress' ? resource(PROGRESS) : resource(GRAPH)))

    render(<Dashboard />)

    for (const tile of ['retention', 'mastery', 'calibration', 'bypass-rate']) {
      expect(screen.getByTestId(`dashboard-tile-${tile}`)).toBeVisible()
    }
    expect(screen.getByTestId('dashboard-tile-bypass-rate').querySelector('[data-testid=delta]')).toHaveTextContent('just now')

    const table = screen.getByTestId('dashboard-mastery-per-concept-table')
    expect(table.querySelectorAll('[data-testid=rep-count]')).toHaveLength(2)
    expect(table.querySelectorAll('[data-testid=locked-concept]')).toHaveLength(1)

    expect(screen.getByTestId('dashboard-footer')).toHaveTextContent(/review log/i)
  })

  it('renders whichever metric loaded and names the one that did not (failure path B)', () => {
    mockUseWebSession.mockReturnValue(SESSION)
    mockUseApiResource.mockImplementation((path) =>
      path === '/me/progress' ? resource<ProgressResponse>(null, { isError: true, error: new Error('progress down') }) : resource(GRAPH),
    )

    render(<Dashboard />)

    expect(screen.getByTestId('dashboard-tiles-error')).toHaveTextContent('progress down')
    expect(screen.getByTestId('dashboard-mastery-per-concept-table')).toBeInTheDocument()
  })
})
