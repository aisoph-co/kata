import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ItemPublic, ReviewResult } from '@/lib/quiz-types'
import type { WebSession } from '@/lib/session-store'
import { ItemCard } from './ItemCard'

const SESSION: WebSession = {
  personId: 'p1',
  displayName: 'Hugo Marchetti',
  email: 'hugo.marchetti@ferry.example',
  isOperator: false,
  role: 'senior_swe',
  header: 'web:auth0|hugo',
}

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const RESULT: ReviewResult = {
  grade: 1,
  rating: 4,
  correct: true,
  explanation: 'Retries must be safe to repeat.',
  confidence: 3,
  bypassed: false,
  next_due_at: '2026-10-01T00:00:00Z',
  concept: { p_known: 0.7, mastered: false },
}

function mcqItem(): ItemPublic {
  return {
    id: 'item-1',
    concept_id: 'concept-1',
    kind: 'mcq',
    prompt: 'Which HTTP status means the request already succeeded once?',
    payload: { options: ['200', '409', '500'] },
  }
}

describe('ItemCard', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('submits an mcq choice with the stated confidence, and renders the graded result', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, RESULT))
    vi.stubGlobal('fetch', fetchMock)

    render(<ItemCard item={mcqItem()} session={SESSION} onNext={vi.fn()} />)

    fireEvent.click(screen.getByLabelText('409'))
    fireEvent.click(screen.getByTestId('confidence-3'))
    fireEvent.click(screen.getByTestId('submit-answer'))

    await waitFor(() => expect(screen.getByTestId('review-result')).toBeInTheDocument())
    expect(screen.getByTestId('review-explanation')).toHaveTextContent('Retries must be safe to repeat.')

    const [, options] = fetchMock.mock.calls[0]
    const body = JSON.parse(options.body as string)
    expect(body).toMatchObject({ item_id: 'item-1', response: { choice: 1 }, confidence: 3 })
    expect(body.bypassed).toBeUndefined()
  })

  it('"just tell me" submits an empty response with bypassed: true, with no choice required', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ...RESULT, bypassed: true, grade: 0.3 }))
    vi.stubGlobal('fetch', fetchMock)

    render(<ItemCard item={mcqItem()} session={SESSION} onNext={vi.fn()} />)
    fireEvent.click(screen.getByTestId('just-tell-me'))

    await waitFor(() => expect(screen.getByTestId('review-result')).toBeInTheDocument())

    const [, options] = fetchMock.mock.calls[0]
    const body = JSON.parse(options.body as string)
    expect(body).toMatchObject({ item_id: 'item-1', response: {}, bypassed: true })
  })

  it('a 409 idempotency replay renders the original result, never an error state', async () => {
    const replayBody = { ...RESULT, grade: 1 }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(409, replayBody)))

    render(<ItemCard item={mcqItem()} session={SESSION} onNext={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('200'))
    fireEvent.click(screen.getByTestId('submit-answer'))

    await waitFor(() => expect(screen.getByTestId('review-result')).toBeInTheDocument())
    expect(screen.getByTestId('review-result')).toHaveAttribute('data-replay', 'true')
    expect(screen.queryByText(/could not submit/i)).not.toBeInTheDocument()
  })

  it('retrying the same submission reuses the same idempotency key', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, RESULT))
    vi.stubGlobal('fetch', fetchMock)

    render(<ItemCard item={mcqItem()} session={SESSION} onNext={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('200'))
    fireEvent.click(screen.getByTestId('submit-answer'))
    await waitFor(() => expect(screen.getByTestId('review-result')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('submit-again'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    const keys = fetchMock.mock.calls.map(([, options]) => JSON.parse(options.body as string).idempotency_key)
    expect(keys[0]).toBe(keys[1])
  })

  it('teach_back has no gradeable submit — only the bypass path (422 no_grader on every real grade attempt)', () => {
    vi.stubGlobal('fetch', vi.fn())
    const item: ItemPublic = { ...mcqItem(), kind: 'teach_back', payload: {} }

    render(<ItemCard item={item} session={SESSION} onNext={vi.fn()} />)

    expect(screen.queryByTestId('submit-answer')).not.toBeInTheDocument()
    expect(screen.getByTestId('just-tell-me')).toBeInTheDocument()
    expect(screen.getByTestId('teach-back-notice')).toBeInTheDocument()
  })
})
