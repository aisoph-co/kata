import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api-client'
import type { TeamPersonDetailResponse } from '@/lib/team-types'

interface State {
  data: TeamPersonDetailResponse | null
  isPending: boolean
  isError: boolean
  error: Error | null
}

const IDLE: State = { data: null, isPending: false, isError: false, error: null }

/**
 * `GET /team/people/{id}` (spec Flow 5, drill-down): one reportee's own
 * concept-level state. Never fetched until `personId` is set — browsing the
 * heatmap alone must never read a report's detail, since every read here is
 * audited (core spec, Testing; issue's own privacy test). A 403
 * (`outside_subtree` for a person outside the caller's subtree,
 * `unknown_identity`/`not_a_manager` otherwise) surfaces as a plain
 * `ApiError`, the same as `/team/overview` — never a different refusal for
 * a hand-edited id (Flow 5, failure path B).
 */
export function useTeamPersonDetail(header: string, personId: string | null): State {
  const [state, setState] = useState<State>(personId ? { ...IDLE, isPending: true } : IDLE)

  useEffect(() => {
    if (!personId) {
      setState(IDLE)
      return
    }
    let cancelled = false
    setState({ ...IDLE, isPending: true })
    apiFetch<TeamPersonDetailResponse>(`/team/people/${personId}`, { persona: { header } })
      .then((data) => {
        if (!cancelled) setState({ data, isPending: false, isError: false, error: null })
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ data: null, isPending: false, isError: true, error: error as Error })
      })
    return () => {
      cancelled = true
    }
  }, [header, personId])

  return state
}
