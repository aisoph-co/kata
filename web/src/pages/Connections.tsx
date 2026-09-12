import { useEffect, useRef, useState } from 'react'
import { ConceptGraph } from '@/components/ConceptGraph'
import { SourceList } from '@/components/SourceList'
import { TopicCard } from '@/components/TopicCard'
import { useConnectionsData } from '@/hooks/useConnectionsData'
import { useIngestion } from '@/hooks/useIngestion'
import { findOwnTopic } from '@/lib/connections-model'
import { useWebSession } from '@/lib/session-store'

/**
 * Screen 1 / SCREENS.md #02 ("Connections", frame 02) — W3, upgraded by
 * KATA-13/CI1 to wire "Connect team context" to a live ingestion run
 * (`useIngestion`, `POST /admin/ingest`). The snapshot itself still comes
 * from `useConnectionsData` (`GET /me/concept-graph` + `GET /topics`) —
 * `useIngestion`'s own counters give the fast, in-flight "derived so far"
 * read; `data.refetch()` pulls the authoritative graph once a run settles.
 *
 * `design/DESIGN-SYSTEM.md`'s empty-state requirement: this is the state a
 * fresh, unseeded workspace shows — no source list, no stream, no invented
 * curriculum, just the honest "nothing connected yet" and the same
 * "Connect team context" action the populated screen otherwise shows.
 */
export function Connections() {
  const session = useWebSession()
  const data = useConnectionsData(session?.header ?? '')
  const ingestion = useIngestion(session?.header ?? '', data.refetch)
  const mountedAt = useRef(performance.now())
  const [topicsVisibleAtSeconds, setTopicsVisibleAtSeconds] = useState<number | null>(null)

  const hasData = data.topics.length > 0 || data.graph.nodes.length > 0

  useEffect(() => {
    if (hasData && topicsVisibleAtSeconds === null) {
      setTopicsVisibleAtSeconds((performance.now() - mountedAt.current) / 1000)
    }
  }, [hasData, topicsVisibleAtSeconds])

  if (!session) return null

  const ownTopic = findOwnTopic(data.topics, session.role)

  const connectAction = session.isOperator && (
    <div className="connections-connect">
      <button
        type="button"
        data-testid="connections-connect-action"
        disabled={ingestion.status === 'running'}
        onClick={ingestion.start}
      >
        Connect team context
      </button>
      {ingestion.status === 'running' && (
        <p data-testid="connections-ingesting" className="gate-status">
          Ingesting… {ingestion.conceptCount} concept{ingestion.conceptCount === 1 ? '' : 's'} so far.
        </p>
      )}
      {ingestion.status === 'empty' && (
        <p data-testid="connections-no-issues" className="gate-status">
          No issues found.
        </p>
      )}
      {ingestion.status === 'error' && (
        <p data-testid="connections-ingest-error" className="gate-status gate-status--error">
          {ingestion.error}
        </p>
      )}
    </div>
  )

  if (data.isPending) {
    return (
      <section className="connections-screen" aria-label="Connections">
        {connectAction}
        <p data-testid="connections-loading">Loading team context…</p>
      </section>
    )
  }

  if (data.isError) {
    return (
      <section className="connections-screen" aria-label="Connections">
        {connectAction}
        <div data-testid="connections-error" className="gate-card">
          <p className="gate-status gate-status--error">
            Couldn&rsquo;t load team context: {data.error?.message ?? 'unknown error'}
          </p>
          <button type="button" onClick={data.refetch}>
            Retry
          </button>
        </div>
      </section>
    )
  }

  if (!hasData) {
    return (
      <section className="connections-screen" aria-label="Connections">
        {connectAction}
        <div className="empty-state" data-testid="connections-empty">
          <h2 className="empty-state-title">No team context connected yet</h2>
          <p className="empty-state-description">
            Nothing has been connected — no source list, no concept graph, no invented curriculum. Connect a repo,
            issue tracker, release notes, and Slack channel to generate your team&rsquo;s concept map and topics.
          </p>
        </div>
      </section>
    )
  }

  return (
    <section className="connections-screen" aria-label="Connections">
      {connectAction}
      <SourceList />
      <div data-testid="connections-derived-stream" className="derived-stream">
        Derived so far: {data.graph.nodes.length} concept{data.graph.nodes.length === 1 ? '' : 's'}, {data.topics.length}{' '}
        topic{data.topics.length === 1 ? '' : 's'}.
      </div>
      <ConceptGraph graph={data.graph} ownEntryConceptId={ownTopic?.entry_concept_id} />
      <div className="topic-card-grid">
        {data.topics.map((topic) => (
          <TopicCard key={topic.id} topic={topic} isOwnTopic={topic.id === ownTopic?.id} />
        ))}
      </div>
      {topicsVisibleAtSeconds !== null && (
        <span
          data-testid="connections-topics-visible-at"
          data-seconds-since-connect={topicsVisibleAtSeconds.toFixed(2)}
          hidden
        />
      )}
    </section>
  )
}
