import { describe, expect, it } from 'vitest'
import {
  classifyCitation,
  findOwnTopic,
  isolatedConceptIds,
  layoutGraph,
  type ConceptGraphResponse,
  type Topic,
} from './connections-model'

function topic(overrides: Partial<Topic>): Topic {
  return {
    id: 't1',
    course_id: 'c1',
    slug: 'idempotent-retries',
    title: 'Retrying a payment without charging twice',
    description: null,
    persona_role: 'junior_swe',
    entry_concept_id: 'idempotency',
    concept_ids: ['idempotency', 'retry-safety'],
    grounded_in: ['PAY-1847'],
    ...overrides,
  }
}

describe('classifyCitation', () => {
  it('classifies an issue key', () => {
    expect(classifyCitation('PAY-1847')).toBe('issue')
  })

  it('classifies a file#anchor reference as a thread', () => {
    expect(classifyCitation('sprint-history.md#sprint-42--stop-double-charging-current-112-september')).toBe('thread')
  })

  it('classifies a bare file path as a file', () => {
    expect(classifyCitation('release-notes.md')).toBe('file')
  })
})

describe('findOwnTopic', () => {
  it('returns the topic matching the learner’s confirmed role', () => {
    const topics = [topic({ persona_role: 'junior_swe' }), topic({ id: 't2', persona_role: 'pm' })]
    expect(findOwnTopic(topics, 'pm')?.id).toBe('t2')
  })

  it('returns undefined when no role is given or none matches', () => {
    const topics = [topic({ persona_role: 'junior_swe' })]
    expect(findOwnTopic(topics, null)).toBeUndefined()
    expect(findOwnTopic(topics, 'uxd')).toBeUndefined()
  })
})

describe('isolatedConceptIds', () => {
  it('flags nodes with no edge touching them at all', () => {
    const graph: ConceptGraphResponse = {
      nodes: [
        { concept_id: 'a', slug: 'a', title: 'A', p_known: 0, mastered: false, unlocked: true },
        { concept_id: 'b', slug: 'b', title: 'B', p_known: 0, mastered: false, unlocked: true },
        { concept_id: 'c', slug: 'c', title: 'C', p_known: 0, mastered: false, unlocked: false },
      ],
      edges: [{ from_concept_id: 'a', to_concept_id: 'b', kind: 'prerequisite', weight: 1 }],
    }
    expect(isolatedConceptIds(graph)).toEqual(new Set(['c']))
  })
})

describe('layoutGraph', () => {
  it('places a prerequisite chain into increasing columns', () => {
    const graph: ConceptGraphResponse = {
      nodes: [
        { concept_id: 'a', slug: 'a', title: 'A', p_known: 0, mastered: false, unlocked: true },
        { concept_id: 'b', slug: 'b', title: 'B', p_known: 0, mastered: false, unlocked: true },
        { concept_id: 'c', slug: 'c', title: 'C', p_known: 0, mastered: false, unlocked: false },
      ],
      edges: [
        { from_concept_id: 'a', to_concept_id: 'b', kind: 'prerequisite', weight: 1 },
        { from_concept_id: 'b', to_concept_id: 'c', kind: 'prerequisite', weight: 1 },
      ],
    }
    const { nodes } = layoutGraph(graph, 100, 50)
    const byId = Object.fromEntries(nodes.map((n) => [n.concept_id, n]))
    expect(byId.a.x).toBe(0)
    expect(byId.b.x).toBe(100)
    expect(byId.c.x).toBe(200)
  })

  it('does not affect layout with a related edge', () => {
    const graph: ConceptGraphResponse = {
      nodes: [
        { concept_id: 'a', slug: 'a', title: 'A', p_known: 0, mastered: false, unlocked: true },
        { concept_id: 'b', slug: 'b', title: 'B', p_known: 0, mastered: false, unlocked: true },
      ],
      edges: [{ from_concept_id: 'a', to_concept_id: 'b', kind: 'related', weight: 0.5 }],
    }
    const { nodes } = layoutGraph(graph, 100, 50)
    const byId = Object.fromEntries(nodes.map((n) => [n.concept_id, n]))
    expect(byId.a.x).toBe(0)
    expect(byId.b.x).toBe(0)
  })
})
