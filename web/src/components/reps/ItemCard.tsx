import { useState } from 'react'
import { apiFetch, ApiError } from '@/lib/api-client'
import type { ItemPublic, ReviewResponseBody, ReviewResult } from '@/lib/quiz-types'
import type { WebSession } from '@/lib/session-store'

function newIdempotencyKey(): string {
  return crypto.randomUUID()
}

function buildResponse(item: ItemPublic, state: { choice: string; choices: number[]; rating: number | null; text: string }): ReviewResponseBody {
  switch (item.kind) {
    case 'mcq':
      return { choice: Number(state.choice) }
    case 'msq':
      return { choices: state.choices }
    case 'self_rated':
      return { rating: state.rating as number }
    case 'short_answer':
    case 'teach_back':
      return { text: state.text }
  }
}

function canSubmit(item: ItemPublic, state: { choice: string; choices: number[]; rating: number | null; text: string }): boolean {
  switch (item.kind) {
    case 'mcq':
      return state.choice !== ''
    case 'msq':
      return state.choices.length > 0
    case 'self_rated':
      return state.rating !== null
    case 'short_answer':
      return state.text.trim().length > 0
    case 'teach_back':
      return false // no_grader (422) on every submission — bypass is the only path
  }
}

function ResultPanel({ result, replay }: { result: ReviewResult; replay?: boolean }) {
  return (
    <div className="reps-result" data-testid="review-result" data-replay={replay ?? false}>
      {replay && <p className="reps-result-banner">Same submission — showing the original result again.</p>}
      <dl className="reps-result-grid">
        <dt>Grade</dt>
        <dd data-testid="review-grade">{result.grade.toFixed(2)}</dd>
        <dt>Next due</dt>
        <dd data-testid="review-next-due">{new Date(result.next_due_at).toLocaleString()}</dd>
        {result.confidence !== null && (
          <>
            <dt>Confidence</dt>
            <dd>{result.confidence}</dd>
          </>
        )}
      </dl>
      {result.explanation && (
        <p className="reps-explanation" data-testid="review-explanation">
          {result.explanation}
        </p>
      )}
      {result.bypassed && <span className="reps-badge">bypassed</span>}
    </div>
  )
}

/**
 * One item from `GET /me/next`, rendered as the input widget the core spec's
 * `response` shape table names for its kind, confidence captured before
 * reveal, and the "just tell me" bypass (flow 4b). Keyed by `item.id` at the
 * call site so a fresh item remounts instead of needing an effect to reset
 * this component's answer state.
 */
export function ItemCard({ item, session, onNext }: { item: ItemPublic; session: WebSession; onNext: () => void }) {
  const [idempotencyKey] = useState(newIdempotencyKey)
  const [choice, setChoice] = useState('')
  const [choices, setChoices] = useState<number[]>([])
  const [rating, setRating] = useState<number | null>(null)
  const [text, setText] = useState('')
  const [confidence, setConfidence] = useState<number | null>(null)
  const [result, setResult] = useState<ReviewResult | null>(null)
  const [replayResult, setReplayResult] = useState<ReviewResult | null>(null)
  const [isPending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const state = { choice, choices, rating, text }
  const graded = result !== null || replayResult !== null

  function submit(bypass: boolean) {
    setPending(true)
    setError(null)
    const body: Record<string, unknown> = {
      item_id: item.id,
      idempotency_key: idempotencyKey,
      response: bypass ? {} : buildResponse(item, state),
    }
    if (bypass) body.bypassed = true
    if (confidence !== null) body.confidence = confidence

    apiFetch<ReviewResult>('/me/reviews', { persona: { header: session.header }, method: 'POST', body })
      .then((data) => {
        setResult(data)
        setReplayResult(null)
      })
      .catch((cause: unknown) => {
        // Failure path B (flow 4b): a replayed submission is a 409 whose
        // body is the original `ReviewResult` — rendered exactly as a fresh
        // 200 would be, never as an error state.
        if (cause instanceof ApiError && cause.status === 409) {
          setReplayResult(cause.body as ReviewResult)
          return
        }
        setError(cause instanceof Error ? cause.message : 'Could not submit that review.')
      })
      .finally(() => setPending(false))
  }

  return (
    <div className="reps-card" data-testid="quiz-item-card" data-item-id={item.id} data-kind={item.kind} data-graded={graded}>
      <p className="reps-prompt">{item.prompt}</p>

      {item.kind === 'mcq' && (
        <div className="reps-options" data-testid="mcq-options" role="radiogroup">
          {item.payload.options?.map((option, i) => (
            <label key={i} className="reps-option">
              <input type="radio" name={`mcq-${item.id}`} checked={choice === String(i)} onChange={() => setChoice(String(i))} disabled={graded} />
              {option}
            </label>
          ))}
        </div>
      )}

      {item.kind === 'msq' && (
        <div className="reps-options" data-testid="msq-options">
          {item.payload.options?.map((option, i) => (
            <label key={i} className="reps-option">
              <input
                type="checkbox"
                checked={choices.includes(i)}
                disabled={graded}
                onChange={(event) => setChoices((prev) => (event.target.checked ? [...prev, i] : prev.filter((x) => x !== i)))}
              />
              {option}
            </label>
          ))}
        </div>
      )}

      {item.kind === 'self_rated' && (
        <div className="reps-options" data-testid="self-rated-options">
          {[1, 2, 3, 4].map((r) => (
            <button key={r} type="button" data-testid={`rating-${r}`} data-selected={rating === r} disabled={graded} onClick={() => setRating(r)}>
              {r}
            </button>
          ))}
        </div>
      )}

      {item.kind === 'short_answer' && (
        <textarea data-testid="short-answer-text" value={text} disabled={graded} onChange={(event) => setText(event.target.value)} rows={4} />
      )}

      {item.kind === 'teach_back' && (
        <p className="reps-teach-back-note" data-testid="teach-back-notice">
          Teach-back items have no automated grader yet — use "Just tell me" to log this rep and move on.
        </p>
      )}

      {!graded && (
        <div className="reps-confidence" data-testid="confidence-control">
          <span>How confident are you?</span>
          {[1, 2, 3, 4, 5].map((c) => (
            <button key={c} type="button" data-testid={`confidence-${c}`} data-selected={confidence === c} onClick={() => setConfidence(c === confidence ? null : c)}>
              {c}
            </button>
          ))}
        </div>
      )}

      <div className="reps-actions">
        {!graded && item.kind !== 'teach_back' && (
          <button data-primary data-testid="submit-answer" disabled={!canSubmit(item, state) || isPending} onClick={() => submit(false)}>
            Submit
          </button>
        )}
        {graded && (
          <button data-testid="submit-again" disabled={isPending} onClick={() => submit(result?.bypassed ?? false)}>
            Submit again
          </button>
        )}
        {!graded && (
          <button data-testid="just-tell-me" disabled={isPending} onClick={() => submit(true)}>
            Just tell me
          </button>
        )}
        {graded && (
          <button data-testid="next-item" onClick={onNext}>
            Next
          </button>
        )}
      </div>

      {error && <p className="reps-error">{error}</p>}
      {result && <ResultPanel result={result} />}
      {replayResult && <ResultPanel result={replayResult} replay />}
    </div>
  )
}
