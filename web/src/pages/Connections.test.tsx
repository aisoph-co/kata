import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useConnectionsData } from '@/hooks/useConnectionsData'
import { useWebSession } from '@/lib/session-store'
import type { ConceptGraphResponse, Topic } from '@/lib/connections-model'

vi.mock('@/hooks/useConnectionsData', () => ({ useConnectionsData: vi.fn() }))
vi.mock('@/lib/session-store', () => ({ useWebSession: vi.fn() }))

import { Connections } from './Connections'

const mockUseConnectionsData = vi.mocked(useConnectionsData)
const mockUseWebSession = vi.mocked(useWebSession)

const LEARNER = {
  personId: 'p1',
  displayName: 'Hugo Marchetti',
  email: 'hugo.marchetti@ferry.example',
  isOperator: false,
  role: 'junior_swe',
  header: 'web:auth0|hugo',
}

const OPERATOR = { ...LEARNER, personId: 'p9', displayName: 'Quinn Halloran', isOperator: true, role: 'tech_lead' }

const GRAPH: ConceptGraphResponse = {
  nodes: [
    { concept_id: 'idempotency', slug: 'idempotency', title: 'Idempotency', p_known: 0.4, mastered: false, unlocked: true },
    { concept_id: 'retry-safety', slug: 'retry-safety', title: 'Retry safety', p_known: 0, mastered: false, unlocked: false },
  ],
  edges: [{ from_concept_id: 'idempotency', to_concept_id: 'retry-safety', kind: 'prerequisite', weight: 1 }],
}

// Three distinct persona roles (SCREENS.md #02: "three persona topic
// cards"; done check: "Hugo/Daniel/Shane's topic cards differ") — what
// `GET /topics?all_roles=true` returns on one signed-in learner's screen,
// per docs/seed/2-curriculum/topics.json's real seeded shape.
const TOPICS: Topic[] = [
  {
    id: 't1',
    course_id: 'c1',
    slug: 'idempotent-retries',
    title: 'Retrying a payment without charging twice',
    description: 'Sprint 42',
    persona_role: 'junior_swe',
    entry_concept_id: 'idempotency',
    concept_ids: ['idempotency', 'retry-safety'],
    grounded_in: ['PAY-1847', 'sprint-history.md#sprint-42--stop-double-charging-current-112-september'],
  },
  {
    id: 't2',
    course_id: 'c1',
    slug: 'contract-testing-and-provider-drift',
    title: 'Contract testing and provider drift',
    description: null,
    persona_role: 'senior_swe',
    entry_concept_id: 'psp-contract-testing',
    concept_ids: ['psp-contract-testing'],
    grounded_in: ['PAY-1834', 'sprint-history.md#the-adyen-field-change-august'],
  },
  {
    id: 't3',
    course_id: 'c1',
    slug: 'sca-exemption-change',
    title: 'SCA exemption change',
    description: null,
    persona_role: 'pm',
    entry_concept_id: 'sca-exemptions',
    concept_ids: ['sca-exemptions'],
    grounded_in: ['PAY-1870', 'company.md#the-live-situation-what-the-team-is-working-on-right-now'],
  },
]

function dataState(overrides: Partial<ReturnType<typeof useConnectionsData>> = {}) {
  return {
    topics: [],
    graph: { nodes: [], edges: [] },
    isPending: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  }
}

describe('Connections', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('renders nothing when there is no session', () => {
    mockUseWebSession.mockReturnValue(null)
    mockUseConnectionsData.mockReturnValue(dataState())

    const { container } = render(<Connections />)

    expect(container).toBeEmptyDOMElement()
  })

  it('shows the loading state while both reads are in flight', () => {
    mockUseWebSession.mockReturnValue(LEARNER)
    mockUseConnectionsData.mockReturnValue(dataState({ isPending: true }))

    render(<Connections />)

    expect(screen.getByTestId('connections-loading')).toBeInTheDocument()
  })

  it('shows a stated error with a retry action on a failed read, never a blank screen', () => {
    mockUseWebSession.mockReturnValue(LEARNER)
    const refetch = vi.fn()
    mockUseConnectionsData.mockReturnValue(dataState({ isError: true, error: new Error('network down'), refetch }))

    render(<Connections />)

    expect(screen.getByTestId('connections-error')).toHaveTextContent('network down')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalled()
  })

  it('shows the honest empty state before any source is connected, with no source list or graph', () => {
    mockUseWebSession.mockReturnValue(LEARNER)
    mockUseConnectionsData.mockReturnValue(dataState())

    render(<Connections />)

    expect(screen.getByTestId('connections-empty')).toBeInTheDocument()
    expect(screen.queryByTestId('connections-source-list')).not.toBeInTheDocument()
    expect(screen.queryByTestId('connections-concept-graph')).not.toBeInTheDocument()
  })

  it('only an operator sees the Connect team context action', () => {
    mockUseWebSession.mockReturnValue(LEARNER)
    mockUseConnectionsData.mockReturnValue(dataState())
    const { rerender } = render(<Connections />)
    expect(screen.queryByTestId('connections-connect-action')).not.toBeInTheDocument()

    mockUseWebSession.mockReturnValue(OPERATOR)
    rerender(<Connections />)
    expect(screen.getByTestId('connections-connect-action')).toBeInTheDocument()
  })

  it('renders three distinct persona topic cards spanning roles, highlighting only the learner’s own', () => {
    mockUseWebSession.mockReturnValue(LEARNER)
    mockUseConnectionsData.mockReturnValue(dataState({ topics: TOPICS, graph: GRAPH }))

    render(<Connections />)

    expect(screen.getByTestId('connections-source-list')).toBeInTheDocument()
    expect(screen.getByTestId('connections-concept-graph')).toBeInTheDocument()

    const cards = screen.getAllByTestId('persona-topic-card')
    expect(cards).toHaveLength(3)
    expect(cards.map((card) => card.textContent)).toEqual([
      expect.stringContaining('Retrying a payment without charging twice'),
      expect.stringContaining('Contract testing and provider drift'),
      expect.stringContaining('SCA exemption change'),
    ])

    // LEARNER is junior_swe — only the matching card (t1) is "own".
    expect(cards[0].className).toContain('topic-card--own')
    expect(cards[1].className).not.toContain('topic-card--own')
    expect(cards[2].className).not.toContain('topic-card--own')

    expect(screen.getAllByTestId('cited-issue-id').length).toBeGreaterThan(0)
    expect(screen.getAllByTestId('cited-thread').length).toBeGreaterThan(0)
  })

  it('highlights the graph’s learner-own node from the topic matching the learner’s confirmed role, not just the first topic', () => {
    mockUseWebSession.mockReturnValue(LEARNER)
    mockUseConnectionsData.mockReturnValue(dataState({ topics: [...TOPICS].reverse(), graph: GRAPH }))

    render(<Connections />)

    // Reversed order: pm (t3) first, junior_swe (t1) last — still finds t1.
    expect(screen.getByTestId('learner-topic-highlighted')).toBeInTheDocument()
    const cards = screen.getAllByTestId('persona-topic-card')
    const ownCard = cards.find((card) => card.className.includes('topic-card--own'))
    expect(ownCard).toHaveTextContent('Retrying a payment without charging twice')
  })

  it('clicking a citation chip opens its excerpt in place, not a new tab', () => {
    mockUseWebSession.mockReturnValue(LEARNER)
    mockUseConnectionsData.mockReturnValue(dataState({ topics: TOPICS, graph: GRAPH }))

    render(<Connections />)

    expect(screen.queryByTestId('connections-excerpt-panel')).not.toBeInTheDocument()
    // Card 1 (t1, PAY-1847) is first — its chip is the first `cited-issue-id`.
    fireEvent.click(screen.getAllByTestId('cited-issue-id')[0])
    expect(screen.getByTestId('connections-excerpt-panel')).toHaveTextContent(/payment intent/)
  })
})
