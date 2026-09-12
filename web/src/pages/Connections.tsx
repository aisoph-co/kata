import { useEffect, useRef, useState } from 'react'
import { ConceptGraph } from '@/components/ConceptGraph'
import { SourceList } from '@/components/SourceList'
import { TopicCard } from '@/components/TopicCard'
import { useConnectionsData } from '@/hooks/useConnectionsData'
import { findOwnTopic } from '@/lib/connections-model'
import { useWebSession } from '@/lib/session-store'

/**
 * Screen 1 / SCREENS.md #02 ("Connections", frame 02) — W3. Renders from
 * the already-loaded seed (`GET /me/concept-graph`, `GET /topics`), not a
 * live ingestion run: Stage 2's CI1 upgrades this same screen to stream a
 * live run, additive to this issue's own scope.
 *
 * `design/DESIGN-SYSTEM.md`'s empty-state requirement: this is the state a
 * fresh, unseeded workspace shows — no source list, no stream, no invented
 * curriculum, just the honest "nothing connected yet" and the same
 * "Connect team context" action the populated screen otherwise shows.
 */
export function Connections() {
  const session = useWebSession()
  const data = useConnectionsData(session?.header ?? '')
  const mountedAt = useRef(performance.now())
  const [topicsVisibleAtSeconds, setTopicsVisibleAtSeconds] = useState<number | null>(null)
  const [connectNote, setConnectNote] = useState<string | null>(null)

  const hasData = data.topics.length > 0 || data.graph.nodes.length > 0

  useEffect(() => {
    if (hasData && topicsVisibleAtSeconds === null) {
      setTopicsVisibleAtSeconds((performance.now() - mountedAt.current) / 1000)
    }
  }, [hasData, topicsVisibleAtSeconds])

  if (!session) return null

  const ownTopic = findOwnTopic(data.topics, session.role)

  // No ingestion-trigger endpoint exists yet (sub-project 4, CI1) — the
  // action is a real, present click target (both states show it, per the
  // empty-state requirement above) but honestly states the gap rather than
  // pretending to start a run that has nowhere to start.
  const connectAction = session.isOperator && (
    <div className="connections-connect">
      <button
        type="button"
        data-testid="connections-connect-action"
        onClick={() => setConnectNote('Ingestion trigger is not wired yet — CI1 adds the live run behind this action.')}
      >
        Connect team context
      </button>
      {connectNote && <p className="gate-status">{connectNote}</p>}
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
