import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api-client'
import type { TeamOverviewResponse } from '@/lib/team-types'

interface State {
  data: TeamOverviewResponse | null
  isPending: boolean
  isError: boolean
  error: Error | null
}

const IDLE: State = { data: null, isPending: true, isError: false, error: null }

/**
 * `GET /team/overview` (spec Flow 5, manager happy path): the acting
 * manager's subtree aggregates — the heatmap's team-mean row and adherence
 * column, and the side panel's team-gap/gone-quiet call-outs. A 403
 * (`not_a_manager` for a person with no reports, `unknown_identity` for an
 * unresolved one) surfaces as `isError` carrying the same `ApiError` every
 * other screen already handles — this hook never renders error UI itself
 * (Flow 5, failure path B: never a different, web-specific error page).
 */
export function useTeamOverview(header: string): State {
  const [state, setState] = useState<State>(IDLE)

  useEffect(() => {
    let cancelled = false
    setState(IDLE)
    apiFetch<TeamOverviewResponse>('/team/overview', { persona: { header } })
      .then((data) => {
        if (!cancelled) setState({ data, isPending: false, isError: false, error: null })
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ data: null, isPending: false, isError: true, error: error as Error })
      })
    return () => {
      cancelled = true
    }
  }, [header])

  return state
}
