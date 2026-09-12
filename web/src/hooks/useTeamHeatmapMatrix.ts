import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api-client'
import type { TeamConceptDetailResponse } from '@/lib/team-types'

export interface HeatmapCell {
  p_known: number
  mastered: boolean
}

/** `person_id -> concept_id -> cell`. A subtree member absent from a
 * concept's `people` array (spec Flow 5, failure path A: "a subtree member
 * with no data") has no entry here at all — the heatmap renders that as an
 * explicit "no reps yet" cell rather than treating a missing lookup as 0. */
export type HeatmapMatrix = Record<string, Record<string, HeatmapCell>>

interface Fetched {
  key: string
  matrix: HeatmapMatrix
  isError: boolean
  error: Error | null
}

interface State {
  matrix: HeatmapMatrix
  isPending: boolean
  isError: boolean
  error: Error | null
}

const EMPTY: Fetched = { key: '', matrix: {}, isError: false, error: null }

/**
 * One `GET /team/concepts/{id}` call per concept in `conceptIds`, fetched
 * in parallel and assembled into a full person x concept matrix — the
 * contract has no single endpoint for the whole heatmap at once (see
 * `TeamConceptDetailResponse`'s own doc comment). `conceptIds` is itself
 * derived from an earlier fetch (`overview.data.concepts`), so it changes
 * on its own schedule — `isPending` is derived from comparing the *current*
 * `key` against the last-completed fetch's key, not a boolean flipped by
 * the effect, so there is no render where a stale "not pending" from a
 * previous, now-superseded `conceptIds` briefly reads as done.
 */
export function useTeamHeatmapMatrix(header: string, conceptIds: readonly string[]): State {
  const key = conceptIds.join(',')
  const [fetched, setFetched] = useState<Fetched>(EMPTY)

  useEffect(() => {
    if (conceptIds.length === 0) {
      setFetched({ key, matrix: {}, isError: false, error: null })
      return
    }
    let cancelled = false
    Promise.all(
      conceptIds.map((conceptId) =>
        apiFetch<TeamConceptDetailResponse>(`/team/concepts/${conceptId}`, { persona: { header } }),
      ),
    )
      .then((responses) => {
        if (cancelled) return
        const matrix: HeatmapMatrix = {}
        for (const response of responses) {
          for (const person of response.people) {
            const row = (matrix[person.person_id] ??= {})
            row[response.concept_id] = { p_known: person.p_known, mastered: person.mastered }
          }
        }
        setFetched({ key, matrix, isError: false, error: null })
      })
      .catch((error: unknown) => {
        if (!cancelled) setFetched({ key, matrix: {}, isError: true, error: error as Error })
      })
    return () => {
      cancelled = true
    }
    // `conceptIds` is a fresh array on every render of the caller (derived
    // from `overview.data`); `key` is the stable dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [header, key])

  const isPending = conceptIds.length > 0 && fetched.key !== key
  return { matrix: fetched.matrix, isPending, isError: fetched.isError, error: fetched.error }
}
