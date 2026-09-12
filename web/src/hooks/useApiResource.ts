import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '@/lib/api-client'
import type { WebSession } from '@/lib/session-store'

interface ResourceState<T> {
  data: T | null
  isPending: boolean
  isError: boolean
  error: Error | null
  /** Re-runs the same GET — the dashboard's four tiles and the quiz queue
   * both need this after a review is submitted (flows.md #5: "live-updating
   * within 5 seconds of a rep taken on any surface"). */
  refetch: () => void
}

/**
 * One GET against the core, scoped to the acting session's `X-Acting-Identity`
 * header — the shared shape behind `useProgress`/`useConceptGraph`/
 * `useNextItems`. `session` is nullable so a caller rendered before
 * `SessionGate` resolves one is still a safe no-op, matching
 * `useSessionResolve`'s null-identity behaviour.
 */
export function useApiResource<T>(path: string, session: WebSession | null): ResourceState<T> {
  const [state, setState] = useState<Omit<ResourceState<T>, 'refetch'>>({
    data: null,
    isPending: session !== null,
    isError: false,
    error: null,
  })
  const generation = useRef(0)

  const load = useCallback(() => {
    if (!session) {
      setState({ data: null, isPending: false, isError: false, error: null })
      return
    }
    const gen = ++generation.current
    setState((prev) => ({ ...prev, isPending: true, isError: false, error: null }))
    apiFetch<T>(path, { persona: { header: session.header } })
      .then((data) => {
        if (gen === generation.current) setState({ data, isPending: false, isError: false, error: null })
      })
      .catch((error: unknown) => {
        if (gen === generation.current) setState({ data: null, isPending: false, isError: true, error: error as Error })
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, session?.header])

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load])

  return { ...state, refetch: load }
}
