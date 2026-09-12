import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api-client'
import type { AuditResponse } from '@/lib/team-types'

interface State {
  data: AuditResponse | null
  isPending: boolean
  isError: boolean
  error: Error | null
}

const IDLE: State = { data: null, isPending: true, isError: false, error: null }

/**
 * `GET /team/audit` — refetches whenever `refreshKey` changes, so the
 * caller bumps it every time a drill-down panel opens (issue: "the audit
 * line updates on open, not only on the parent screen's load").
 */
export function useTeamAudit(header: string, refreshKey: number): State {
  const [state, setState] = useState<State>(IDLE)

  useEffect(() => {
    let cancelled = false
    setState((prev) => ({ ...prev, isPending: true }))
    apiFetch<AuditResponse>('/team/audit', { persona: { header } })
      .then((data) => {
        if (!cancelled) setState({ data, isPending: false, isError: false, error: null })
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ data: null, isPending: false, isError: true, error: error as Error })
      })
    return () => {
      cancelled = true
    }
    // `refreshKey` is the deliberate re-fetch trigger, not `header` alone.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [header, refreshKey])

  return state
}
