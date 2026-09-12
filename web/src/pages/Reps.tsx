import { useState } from 'react'
import { ItemCard } from '@/components/reps/ItemCard'
import { useApiResource } from '@/hooks/useApiResource'
import type { NextItemsResponse } from '@/lib/quiz-types'
import { useWebSession } from '@/lib/session-store'

const REASON_COPY: Record<string, string> = {
  all_mastered: "You've mastered every unlocked concept — nothing is due right now.",
  blocked_by_prerequisites: 'Nothing is due, and the rest is behind a prerequisite you have not unlocked yet.',
}

/**
 * The quiz-taking engine (W2, flow 4b): `GET /me/next` up to 5 items,
 * overdue first, rendered one at a time. Failure path A (empty queue) shows
 * the served `reason`, not a blank state or an invented message.
 */
export function Reps() {
  const session = useWebSession()
  const next = useApiResource<NextItemsResponse>('/me/next', session)
  const [index, setIndex] = useState(0)

  if (!session) return null
  if (next.isPending) return <p data-testid="reps-loading">Loading your next reps…</p>
  if (next.isError) return <p data-testid="reps-error">Could not load your next reps: {next.error?.message}</p>

  const items = next.data?.items ?? []
  const current = items[index]

  if (items.length === 0) {
    const reason = next.data?.reason
    return (
      <p data-testid="reps-empty" data-reason={reason}>
        {(reason && REASON_COPY[reason]) ?? 'Nothing is due right now.'}
      </p>
    )
  }

  function advance() {
    if (index + 1 < items.length) {
      setIndex((i) => i + 1)
    } else {
      setIndex(0)
      next.refetch()
    }
  }

  return (
    <div className="reps-screen">
      <p className="reps-position" data-testid="reps-position">
        {index + 1} of {items.length}
      </p>
      {current && <ItemCard key={current.id} item={current} session={session} onNext={advance} />}
    </div>
  )
}
