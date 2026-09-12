/**
 * Screen 2 (`build-day/SCREENS.md` #02, "Connections") — pure, testable
 * pieces of the concept-graph / topics rendering (`contracts/openapi.yaml`
 * `ConceptGraphResponse`, `TopicsResponse`). Kept out of `Connections.tsx`
 * so layout and citation classification can be unit-tested without a DOM.
 */

export interface ConceptGraphNode {
  concept_id: string
  slug: string
  title: string
  p_known: number
  mastered: boolean
  unlocked: boolean
}

export type ConceptEdgeKind = 'prerequisite' | 'related'

export interface ConceptEdge {
  id?: string
  from_concept_id: string
  to_concept_id: string
  kind: ConceptEdgeKind
  weight: number
}

export interface ConceptGraphResponse {
  nodes: ConceptGraphNode[]
  edges: ConceptEdge[]
}

/** Roster's role enum (`contracts/openapi.yaml` `Topic.persona_role`) —
 * duplicated from `pages/RoleRequired.tsx` rather than imported, so this
 * issue's files don't reach into W1's. */
export type PersonaRole = 'tech_lead' | 'senior_swe' | 'junior_swe' | 'pm' | 'uxd'

export const ROLE_LABEL: Record<PersonaRole, string> = {
  tech_lead: 'Tech lead',
  senior_swe: 'Senior SWE',
  junior_swe: 'Junior SWE',
  pm: 'PM',
  uxd: 'UX designer',
}

export interface Topic {
  id: string
  course_id: string
  slug: string
  title: string
  description: string | null
  persona_role: PersonaRole
  entry_concept_id: string
  concept_ids: string[]
  grounded_in: string[]
}

export interface TopicsResponse {
  topics: Topic[]
}

export const EMPTY_GRAPH: ConceptGraphResponse = { nodes: [], edges: [] }

/**
 * A `grounded_in` entry (`Topic.grounded_in`, KAT-C1/C2) is one of: an issue
 * key (`PAY-1847`), a file path with an optional heading anchor
 * (`sprint-history.md#sprint-42--...`), or bare a file path with no anchor.
 * The issue key shape is the roster's own convention (see `docs/seed`); an
 * anchor is what turns a citation into "a thread" per the issue text
 * ("an issue id, file path, release version, or thread reference").
 */
export type CitationKind = 'issue' | 'thread' | 'file'

const ISSUE_KEY = /^[A-Z][A-Z0-9]+-\d+$/

export function classifyCitation(citation: string): CitationKind {
  if (ISSUE_KEY.test(citation)) return 'issue'
  if (citation.includes('#')) return 'thread'
  return 'file'
}

/** The topic that names the signed-in learner's own confirmed role, if any
 * — SCREENS.md #02's "the learner's own topic highlighted." A role can hold
 * more than one topic (`docs/seed/2-curriculum/topics.json` `_fields`); the
 * first is the one entry point the graph highlights. */
export function findOwnTopic(topics: Topic[], role: string | null): Topic | undefined {
  if (!role) return undefined
  return topics.find((topic) => topic.persona_role === role)
}

/** Concepts with no edge touching them at all — the real, derivable analogue
 * of "concepts still being produced" (SCREENS.md #02) available from a
 * `ConceptGraphResponse` snapshot alone: a node ingestion has written but not
 * yet linked into the prerequisite/related graph. Rendered dashed. */
export function isolatedConceptIds(graph: ConceptGraphResponse): Set<string> {
  const connected = new Set<string>()
  for (const edge of graph.edges) {
    connected.add(edge.from_concept_id)
    connected.add(edge.to_concept_id)
  }
  return new Set(graph.nodes.filter((node) => !connected.has(node.concept_id)).map((node) => node.concept_id))
}

export interface LaidOutNode extends ConceptGraphNode {
  x: number
  y: number
}

export interface GraphLayout {
  nodes: LaidOutNode[]
  columnWidth: number
  rowHeight: number
}

/**
 * Deterministic layered layout: a node's column is its longest
 * `prerequisite`-edge distance from a root (a node no prerequisite edge
 * points at); ties within a column stack by row. `related` edges don't
 * affect layout, only how the edge itself is drawn. Kahn's algorithm over
 * `prerequisite` edges only, so a cycle (which the core rejects at
 * ingestion, KAT-C1) can't hang this — any node left unprocessed by the
 * queue is placed in column 0.
 */
export function layoutGraph(graph: ConceptGraphResponse, columnWidth = 200, rowHeight = 96): GraphLayout {
  const depth = new Map<string, number>()
  const prerequisiteEdges = graph.edges.filter((edge) => edge.kind === 'prerequisite')
  const outgoing = new Map<string, string[]>()
  const indegree = new Map<string, number>()
  for (const node of graph.nodes) indegree.set(node.concept_id, 0)
  for (const edge of prerequisiteEdges) {
    if (!outgoing.has(edge.from_concept_id)) outgoing.set(edge.from_concept_id, [])
    outgoing.get(edge.from_concept_id)!.push(edge.to_concept_id)
    indegree.set(edge.to_concept_id, (indegree.get(edge.to_concept_id) ?? 0) + 1)
    if (!depth.has(edge.from_concept_id)) depth.set(edge.from_concept_id, 0)
  }

  const queue: string[] = graph.nodes.filter((n) => (indegree.get(n.concept_id) ?? 0) === 0).map((n) => n.concept_id)
  for (const id of queue) if (!depth.has(id)) depth.set(id, 0)
  const remaining = new Map(indegree)
  while (queue.length) {
    const id = queue.shift()!
    const here = depth.get(id) ?? 0
    for (const next of outgoing.get(id) ?? []) {
      depth.set(next, Math.max(depth.get(next) ?? 0, here + 1))
      const left = (remaining.get(next) ?? 0) - 1
      remaining.set(next, left)
      if (left === 0) queue.push(next)
    }
  }

  const perColumn = new Map<number, number>()
  const nodes: LaidOutNode[] = graph.nodes.map((node) => {
    const column = depth.get(node.concept_id) ?? 0
    const row = perColumn.get(column) ?? 0
    perColumn.set(column, row + 1)
    return { ...node, x: column * columnWidth, y: row * rowHeight }
  })

  return { nodes, columnWidth, rowHeight }
}
