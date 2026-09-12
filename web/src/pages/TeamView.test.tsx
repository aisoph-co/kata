import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearWebSession, setWebSession } from '@/lib/session-store'
import { TeamView } from './TeamView'

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

const OVERVIEW = {
  concepts: [
    { concept_id: 'c-idempotency', mean_mastery: 0.9, share_mastered: 0.8, at_risk_count: 0 },
    { concept_id: 'c-sca-exemptions', mean_mastery: 0.2, share_mastered: 0.1, at_risk_count: 4 },
  ],
  people: [
    { person_id: 'p-hugo', adherence: 0.9, velocity: 3, last_active: '2026-09-11T00:00:00Z', bypass_rate: 0.05 },
    { person_id: 'p-nushka', adherence: 0.1, velocity: 1, last_active: null, bypass_rate: 0.4 },
  ],
  retention: { d1: { accuracy: 0.9, samples: 20 }, d7: { accuracy: 0.7, samples: 10 }, d30: { accuracy: null, samples: 2 } },
}

const CONCEPT_GRAPH = {
  nodes: [
    { concept_id: 'c-idempotency', slug: 'idempotency', title: 'Idempotency', p_known: 0.2, mastered: false, unlocked: true },
    { concept_id: 'c-sca-exemptions', slug: 'sca-exemptions', title: 'SCA exemptions', p_known: 0.2, mastered: false, unlocked: true },
  ],
  edges: [],
}

function conceptDetail(conceptId: string, people: Array<{ person_id: string; p_known: number; mastered: boolean }>) {
  return { concept_id: conceptId, people }
}

function personDetail(personId: string) {
  return {
    person_id: personId,
    concepts: [{ concept_id: 'c-idempotency', p_known: 0.9, mastered: true, due_count: 0, unlocked: true }],
    adherence: 0.9,
    velocity: 3,
    due_count: 0,
    last_active: '2026-09-11T00:00:00Z',
    bypass_rate: 0.05,
    retention: OVERVIEW.retention,
    calibration: 0.1,
  }
}

function routeFetch(url: string): Response {
  if (url.endsWith('/team/overview')) return jsonResponse(200, OVERVIEW)
  if (url.endsWith('/me/concept-graph')) return jsonResponse(200, CONCEPT_GRAPH)
  if (url.endsWith('/team/concepts/c-idempotency')) {
    return jsonResponse(
      200,
      conceptDetail('c-idempotency', [
        { person_id: 'p-hugo', p_known: 0.9, mastered: true },
        { person_id: 'p-nushka', p_known: 0.3, mastered: false },
      ]),
    )
  }
  if (url.endsWith('/team/concepts/c-sca-exemptions')) {
    // p-nushka has no reps yet on this concept — omitted, not zeroed.
    return jsonResponse(200, conceptDetail('c-sca-exemptions', [{ person_id: 'p-hugo', p_known: 0.2, mastered: false }]))
  }
  if (url.endsWith('/team/audit')) {
    return jsonResponse(200, {
      entries: [
        { id: 'a1', actor_person_id: 'p-quinn', subject_scope: 'p-hugo', endpoint: '/team/people/p-hugo', at: '2026-09-12T00:00:00Z' },
      ],
    })
  }
  if (url.includes('/team/people/')) return jsonResponse(200, personDetail(url.split('/').pop()!))
  throw new Error(`unhandled fetch: ${url}`)
}

describe('TeamView', () => {
  beforeEach(() => {
    setWebSession({
      personId: 'p-quinn',
      displayName: 'Quinn',
      email: 'quinn@ferry.example',
      isOperator: false,
      role: 'tech_lead',
      header: 'web:quinn',
    })
    vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(routeFetch(url))))
  })

  afterEach(() => {
    clearWebSession()
    vi.unstubAllGlobals()
  })

  it('renders the heatmap, adherence column, team-mean row, and audit badges', async () => {
    render(<TeamView />)

    await screen.findByTestId('team-heatmap')
    expect(screen.getByTestId('team-badge-concept-level')).toBeInTheDocument()
    expect(screen.getByTestId('team-badge-audited')).toBeInTheDocument()

    // Concept titles resolved from /me/concept-graph, not raw ids.
    const heatmap = screen.getByTestId('team-heatmap')
    expect(await within(heatmap).findByText('Idempotency')).toBeInTheDocument()
    expect(within(heatmap).getByText('SCA exemptions')).toBeInTheDocument()

    // Adherence column.
    expect(screen.getByTestId('team-adherence-p-hugo')).toHaveTextContent('90%')

    // Team-mean row.
    const meanRow = screen.getByTestId('team-mean-row')
    expect(meanRow).toHaveTextContent('90%')
    expect(meanRow).toHaveTextContent('20%')

    // A subtree member missing from a concept's detail renders as an
    // explicit "no reps yet" cell, never a silently-omitted row.
    expect(screen.getAllByTestId('heatmap-cell-empty')).toHaveLength(1)
  })

  it('computes the team gap and gone-quiet call-outs from the overview', async () => {
    render(<TeamView />)

    await screen.findByTestId('team-heatmap')

    // Wait for /me/concept-graph's titles to resolve before asserting on
    // them, same signal the heatmap's own column headers depend on.
    await within(screen.getByTestId('team-heatmap')).findByText('SCA exemptions')

    expect(await screen.findByTestId('team-gap-callout')).toHaveTextContent('SCA exemptions')
    expect(screen.getByTestId('team-gone-quiet-callout')).toHaveTextContent('10%')
  })

  it('opens a drill-down on row click, fetches only that person, and refreshes the audit line', async () => {
    render(<TeamView />)

    await screen.findByTestId('team-heatmap')
    const fetchMock = vi.mocked(fetch)
    const callsBeforeClick = fetchMock.mock.calls.length

    fireEvent.click(screen.getByTestId('team-row-p-hugo'))

    await screen.findByTestId('team-drilldown')
    expect(screen.getByTestId('team-drilldown-concepts')).toBeInTheDocument()

    const detailCall = fetchMock.mock.calls.slice(callsBeforeClick).find(([url]) => String(url).includes('/team/people/'))
    expect(detailCall?.[0]).toBe('/api/team/people/p-hugo')

    // Opening the panel is one more /team/audit read than the initial load.
    const auditCallsAfter = fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/team/audit')).length
    expect(auditCallsAfter).toBeGreaterThanOrEqual(2)

    // The response this panel renders (`personDetail`, above) carries only
    // `ProgressEntry`/summary fields — no `answer`/item/transcript field
    // exists to leak; the panel's own privacy note says so explicitly.
    expect(screen.getByTestId('team-drilldown-privacy-note')).toHaveTextContent(/transcript/i)
  })

  it('shows the same forbidden treatment on a 403, never a bespoke error page', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(403, { detail: { code: 'not_a_manager', message: 'no reports' } })))

    render(<TeamView />)

    expect(await screen.findByTestId('team-view-forbidden')).toBeInTheDocument()
    expect(screen.queryByTestId('team-heatmap')).not.toBeInTheDocument()
  })
})
