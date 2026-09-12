import { describe, expect, it } from 'vitest'
import { goneQuiet, pmAsymmetry, teamGap } from './team-callouts'
import type { TeamConceptSummary, TeamPersonSummary } from './team-types'
import type { HeatmapMatrix } from '@/hooks/useTeamHeatmapMatrix'

function concept(id: string, meanMastery: number, shareMastered = 0.5): TeamConceptSummary {
  return { concept_id: id, mean_mastery: meanMastery, share_mastered: shareMastered, at_risk_count: 0 }
}

function person(id: string, adherence: number): TeamPersonSummary {
  return { person_id: id, adherence, velocity: 1, last_active: null, bypass_rate: null }
}

describe('teamGap', () => {
  it('is null for an empty subtree', () => {
    expect(teamGap([])).toBeNull()
  })

  it('picks the lowest mean_mastery concept', () => {
    const concepts = [concept('a', 0.7), concept('b', 0.3, 0.1), concept('c', 0.9)]
    expect(teamGap(concepts)).toEqual({ conceptId: 'b', meanMastery: 0.3, shareMastered: 0.1 })
  })
})

describe('goneQuiet', () => {
  it('is null with no people', () => {
    expect(goneQuiet([])).toBeNull()
  })

  it('picks the lowest-adherence person', () => {
    const people = [person('p1', 0.9), person('p2', 0.2), person('p3', 0.6)]
    expect(goneQuiet(people)).toEqual({ personId: 'p2', adherence: 0.2 })
  })
})

describe('pmAsymmetry', () => {
  it('is null when no one clears the gap threshold', () => {
    const matrix: HeatmapMatrix = {
      p1: { c1: { p_known: 0.5, mastered: false }, c2: { p_known: 0.55, mastered: false }, c3: { p_known: 0.5, mastered: false } },
    }
    expect(pmAsymmetry(matrix, ['c1', 'c2', 'c3'])).toBeNull()
  })

  it('is null for a person with too few concepts of data', () => {
    const matrix: HeatmapMatrix = {
      p1: { c1: { p_known: 0.95, mastered: true }, c2: { p_known: 0.1, mastered: false } },
    }
    expect(pmAsymmetry(matrix, ['c1', 'c2'])).toBeNull()
  })

  it('flags a role expert on exactly one mastered concept', () => {
    const matrix: HeatmapMatrix = {
      p1: {
        c1: { p_known: 0.95, mastered: true },
        c2: { p_known: 0.1, mastered: false },
        c3: { p_known: 0.15, mastered: false },
      },
      p2: {
        c1: { p_known: 0.5, mastered: false },
        c2: { p_known: 0.5, mastered: false },
        c3: { p_known: 0.5, mastered: false },
      },
    }
    expect(pmAsymmetry(matrix, ['c1', 'c2', 'c3'])).toEqual({
      personId: 'p1',
      conceptId: 'c1',
      pKnown: 0.95,
      restMean: 0.125,
    })
  })
})
