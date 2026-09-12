import { MasteryChart } from '@/components/dashboard/MasteryChart'
import { useApiResource } from '@/hooks/useApiResource'
import { formatPercent, formatRelativeDelta, formatSigned } from '@/lib/format'
import type { ConceptGraphResponse, ProgressResponse } from '@/lib/quiz-types'
import { useWebSession } from '@/lib/session-store'

function Tile({ testId, label, value, caption, delta }: { testId: string; label: string; value: string; caption?: string; delta?: string | null }) {
  return (
    <div className="dashboard-tile" data-testid={testId}>
      <p className="dashboard-tile-label">{label}</p>
      <p className="dashboard-tile-value">{value}</p>
      {caption && <p className="dashboard-tile-caption">{caption}</p>}
      {delta && (
        <span className="dashboard-tile-delta" data-testid="delta">
          {delta}
        </span>
      )}
    </div>
  )
}

/**
 * The personal dashboard (W2, frame 09): four tiles from `/me/progress`,
 * the 30-day mastery chart (R3b), and the mastery-per-concept table
 * (R3a — rep count degrades to "—", `/me/concept-graph` supplies the
 * names `/me/progress` doesn't carry).
 */
export function Dashboard() {
  const session = useWebSession()
  const progress = useApiResource<ProgressResponse>('/me/progress', session)
  const graph = useApiResource<ConceptGraphResponse>('/me/concept-graph', session)

  if (!session) return null
  if (progress.isPending || graph.isPending) return <p data-testid="dashboard-loading">Loading your progress…</p>

  // Failure path B (flows.md #5): render whichever metrics loaded and name
  // the one that didn't, rather than blanking the whole screen.
  if (progress.isError && graph.isError) {
    return <p data-testid="dashboard-error">Could not load your progress: {progress.error?.message}</p>
  }

  const summary = progress.data?.summary ?? null
  const concepts = progress.data?.concepts ?? []
  const masteredCount = concepts.filter((c) => c.mastered).length
  const nodes = graph.data?.nodes ?? []

  return (
    <div className="dashboard-screen">
      <div className="dashboard-tiles">
        <Tile
          testId="dashboard-tile-retention"
          label="Retention"
          value={
            summary
              ? `1d ${formatPercent(summary.retention.d1.accuracy)} · 7d ${formatPercent(summary.retention.d7.accuracy)} · 30d ${formatPercent(summary.retention.d30.accuracy)}`
              : '—'
          }
          caption="Accuracy on reps spaced 1 / 7 / 30 days apart"
        />
        <Tile
          testId="dashboard-tile-mastery"
          label="Mastery"
          value={progress.data ? `${masteredCount} / ${concepts.length}` : '—'}
          caption="Concepts mastered"
        />
        <Tile
          testId="dashboard-tile-calibration"
          label="Calibration"
          value={summary ? formatSigned(summary.calibration) : '—'}
          caption="Confidence vs. accuracy"
        />
        <Tile
          testId="dashboard-tile-bypass-rate"
          label="Bypass rate"
          value={summary ? formatPercent(summary.bypass_rate) : '—'}
          caption="Share of reps answered with “just tell me”"
          delta={summary ? formatRelativeDelta(summary.last_active) : null}
        />
      </div>

      {progress.isError && <p data-testid="dashboard-tiles-error">Tiles could not load: {progress.error?.message}</p>}

      <MasteryChart />

      {graph.isError ? (
        <p data-testid="dashboard-table-error">Mastery-per-concept table could not load: {graph.error?.message}</p>
      ) : (
        <table className="dashboard-mastery-table" data-testid="dashboard-mastery-per-concept-table">
          <thead>
            <tr>
              <th>Concept</th>
              <th>p(known)</th>
              <th>Mastered</th>
              <th>Reps</th>
            </tr>
          </thead>
          <tbody>
            {nodes.map((node) => (
              <tr key={node.concept_id} data-testid={node.unlocked ? undefined : 'locked-concept'} data-locked={!node.unlocked}>
                <td>{node.title}</td>
                <td>{node.p_known.toFixed(2)}</td>
                <td>{node.mastered ? 'Yes' : 'No'}</td>
                {/* R3a (open): `ProgressEntry` has no per-concept rep count
                    on the contract yet — shown as "—", never invented. */}
                <td data-testid="rep-count">—</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <footer className="dashboard-footer" data-testid="dashboard-footer">
        Every number here is rebuilt from the append-only review log.
      </footer>
    </div>
  )
}
