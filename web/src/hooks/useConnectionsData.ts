import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api-client'
import { EMPTY_GRAPH, type ConceptGraphResponse, type Topic, type TopicsResponse } from '@/lib/connections-model'

interface ConnectionsData {
  topics: Topic[]
  graph: ConceptGraphResponse
}

interface ConnectionsDataState extends ConnectionsData {
  isPending: boolean
  isError: boolean
  error: Error | null
  refetch: () => void
}

const IDLE: ConnectionsData = { topics: [], graph: EMPTY_GRAPH }

/**
 * Screen 2's own reads (`R4`/`R5`, `GET /me/concept-graph` + `GET /topics`)
 * — a snapshot of the already-loaded seed, not a live ingestion stream
 * (that upgrade is CI1's, additive to this issue). Both calls run in
 * parallel and share one pending/error state, since the screen has nothing
 * useful to show with only one of the two.
 *
 * `/topics` defaults to the caller's own role (`learning_service/topics.py`)
 * — right for "my topics", wrong for this screen: SCREENS.md #02 shows
 * three persona topic cards side by side on one signed-in learner's own
 * screen, a cross-role view of what ingestion produced for the team, not
 * "my topics". `all_roles=true` (KATA-7/W3, additive — every other caller's
 * default behavior is unchanged) opts this screen out of that filter;
 * topics carry no per-person data, so there's nothing this hides.
 */
export function useConnectionsData(header: string): ConnectionsDataState {
  const [data, setData] = useState<ConnectionsData>(IDLE)
  const [isPending, setIsPending] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setIsPending(true)
    setError(null)

    Promise.all([
      apiFetch<TopicsResponse>('/topics?all_roles=true', { persona: { header } }),
      apiFetch<ConceptGraphResponse>('/me/concept-graph', { persona: { header } }),
    ])
      .then(([topicsResponse, graph]) => {
        if (cancelled) return
        setData({ topics: topicsResponse.topics, graph })
        setIsPending(false)
      })
      .catch((cause: unknown) => {
        if (cancelled) return
        setData(IDLE)
        setError(cause as Error)
        setIsPending(false)
      })

    return () => {
      cancelled = true
    }
  }, [header, attempt])

  return { ...data, isPending, isError: error !== null, error, refetch: () => setAttempt((n) => n + 1) }
}
