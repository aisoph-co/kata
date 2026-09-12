import { isolatedConceptIds, layoutGraph, type ConceptGraphResponse } from '@/lib/connections-model'

const NODE_RADIUS = 28

/**
 * The concept graph (SCREENS.md #02): nodes + prerequisite/related edges
 * from `GET /me/concept-graph`, the learner's own topic's entry concept
 * highlighted, and concepts with no edge yet (see `isolatedConceptIds`)
 * drawn dashed as the still-arriving signal.
 */
export function ConceptGraph({
  graph,
  ownEntryConceptId,
}: {
  graph: ConceptGraphResponse
  ownEntryConceptId: string | undefined
}) {
  const { nodes, columnWidth, rowHeight } = layoutGraph(graph)
  const isolated = isolatedConceptIds(graph)
  const byId = new Map(nodes.map((node) => [node.concept_id, node]))

  const maxColumn = nodes.reduce((max, node) => Math.max(max, node.x), 0)
  const maxRow = nodes.reduce((max, node) => Math.max(max, node.y), 0)
  const width = maxColumn + columnWidth
  const height = maxRow + rowHeight

  return (
    <svg
      className="concept-graph"
      data-testid="connections-concept-graph"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Concept graph"
    >
      <g>
        {graph.edges.map((edge) => {
          const from = byId.get(edge.from_concept_id)
          const to = byId.get(edge.to_concept_id)
          if (!from || !to) return null
          const isPrerequisite = edge.kind === 'prerequisite'
          return (
            <line
              key={`${edge.from_concept_id}->${edge.to_concept_id}:${edge.kind}`}
              data-testid={isPrerequisite ? 'prerequisite-edge' : 'related-edge'}
              x1={from.x + NODE_RADIUS}
              y1={from.y + NODE_RADIUS}
              x2={to.x + NODE_RADIUS}
              y2={to.y + NODE_RADIUS}
              className={isPrerequisite ? 'concept-edge concept-edge--prerequisite' : 'concept-edge concept-edge--related'}
            />
          )
        })}
      </g>
      <g>
        {nodes.map((node) => {
          const isOwn = node.concept_id === ownEntryConceptId
          const isArriving = isolated.has(node.concept_id)
          // `learner-topic-highlighted` wins when a node is both the
          // learner's own entry concept and still-arriving — the e2e
          // contract (`build-day/tests/e2e/test_connections.py`) expects
          // exactly one highlighted node, so it can't be ambiguous between
          // the two testids.
          const testId = isOwn ? 'learner-topic-highlighted' : isArriving ? 'node-arriving' : 'concept-node'
          return (
            <g key={node.concept_id} data-testid={testId} transform={`translate(${node.x}, ${node.y})`}>
              <circle
                r={NODE_RADIUS}
                cx={NODE_RADIUS}
                cy={NODE_RADIUS}
                className={[
                  'concept-node-circle',
                  node.mastered && 'concept-node-circle--mastered',
                  !node.unlocked && 'concept-node-circle--locked',
                  isOwn && 'concept-node-circle--own',
                  isArriving && 'concept-node-circle--arriving',
                ]
                  .filter(Boolean)
                  .join(' ')}
              />
              <text x={NODE_RADIUS} y={NODE_RADIUS * 2 + 14} textAnchor="middle" className="concept-node-label">
                {node.title}
              </text>
            </g>
          )
        })}
      </g>
    </svg>
  )
}
