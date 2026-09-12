import type { HeatmapMatrix } from '@/hooks/useTeamHeatmapMatrix'
import type { TeamConceptSummary, TeamPersonSummary } from '@/lib/team-types'

export interface TeamGap {
  conceptId: string
  meanMastery: number
  shareMastered: number
}

/** The side panel's "team gap": the subtree's lowest-mastery concept, plus
 * its share mastered (issue: "team gap (lowest-mastery concept + share
 * mastered)"). `null` only when the manager's subtree has no concepts at
 * all. */
export function teamGap(concepts: readonly TeamConceptSummary[]): TeamGap | null {
  if (concepts.length === 0) return null
  const lowest = concepts.reduce((min, c) => (c.mean_mastery < min.mean_mastery ? c : min))
  return { conceptId: lowest.concept_id, meanMastery: lowest.mean_mastery, shareMastered: lowest.share_mastered }
}

export interface GoneQuiet {
  personId: string
  adherence: number
}

/** The side panel's "gone quiet": the lowest-adherence person in the
 * subtree (issue: "'gone quiet' (lowest-adherence person)"). */
export function goneQuiet(people: readonly TeamPersonSummary[]): GoneQuiet | null {
  if (people.length === 0) return null
  const lowest = people.reduce((min, p) => (p.adherence < min.adherence ? p : min))
  return { personId: lowest.person_id, adherence: lowest.adherence }
}

export interface PmAsymmetry {
  personId: string
  conceptId: string
  pKnown: number
  restMean: number
}

const ASYMMETRY_MIN_GAP = 0.4
const ASYMMETRY_MIN_CONCEPTS = 3

/**
 * The side panel's "PM-asymmetry note": someone expert on exactly one
 * concept and near-zero on the rest (issue: "a role expert on one concept,
 * near-zero on the rest"). Flags the person/concept pair with the largest
 * gap between that concept's `p_known` and the mean of their other
 * concepts, provided the flagged concept is actually mastered and the gap
 * clears `ASYMMETRY_MIN_GAP` — a person needs at least
 * `ASYMMETRY_MIN_CONCEPTS` concepts of data for "the rest" to mean
 * anything. `null` when no one in the matrix clears the bar (a quiet team
 * has nothing to flag, which is a fine outcome, not a broken one).
 */
export function pmAsymmetry(matrix: HeatmapMatrix, conceptIds: readonly string[]): PmAsymmetry | null {
  let best: PmAsymmetry | null = null
  for (const [personId, row] of Object.entries(matrix)) {
    const cells = conceptIds.map((conceptId) => ({ conceptId, cell: row[conceptId] })).filter((c) => c.cell)
    if (cells.length < ASYMMETRY_MIN_CONCEPTS) continue
    for (const { conceptId, cell } of cells) {
      if (!cell.mastered) continue
      const rest = cells.filter((c) => c.conceptId !== conceptId)
      const restMean = rest.reduce((sum, c) => sum + c.cell.p_known, 0) / rest.length
      const gap = cell.p_known - restMean
      const bestGap = best ? best.pKnown - best.restMean : -Infinity
      if (gap >= ASYMMETRY_MIN_GAP && gap > bestGap) {
        best = { personId, conceptId, pKnown: cell.p_known, restMean }
      }
    }
  }
  return best
}
