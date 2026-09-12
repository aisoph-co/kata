import type { ConceptTitle } from '@/hooks/useConceptTitles'
import type { TeamPersonDetailResponse } from '@/lib/team-types'
import { ApiError } from '@/lib/api-client'
import { conceptLabel, formatPercent, personLabel } from '@/lib/team-format'
import { pKnownBand } from '@/lib/p-known-bands'

interface DrilldownState {
  data: TeamPersonDetailResponse | null
  isPending: boolean
  isError: boolean
  error: Error | null
}

/**
 * The side panel opened by clicking a heatmap row (issue: "Drill-down").
 * Renders exactly `TeamPersonDetailResponse`'s own fields — `p_known`,
 * `mastered`, per-concept retention/calibration where they exist — and
 * nothing else: this component's own privacy contract is that it never
 * reads or renders an `answer`/`item`/transcript field, because the
 * response it's fed never carries one (core spec, Testing).
 */
export function TeamPersonDrilldown({
  personId,
  state,
  conceptTitles,
  onClose,
}: {
  personId: string
  state: DrilldownState
  conceptTitles: Record<string, ConceptTitle>
  onClose: () => void
}) {
  return (
    <div className="team-drilldown" data-testid="team-drilldown" role="dialog" aria-label={personLabel(personId)}>
      <div className="team-drilldown-header">
        <h3>{personLabel(personId)}</h3>
        <button data-testid="team-drilldown-close" onClick={onClose}>
          Close
        </button>
      </div>

      {state.isPending && <p data-testid="team-drilldown-loading">Loading concept-level state…</p>}

      {state.isError && (
        <p data-testid="team-drilldown-error">
          {state.error instanceof ApiError && state.error.status === 403
            ? 'Outside your subtree — same refusal as opening this person directly by id.'
            : "Couldn't load this person's concept-level state."}
        </p>
      )}

      {state.data && (
        <>
          <dl className="team-drilldown-summary">
            <div>
              <dt>Adherence</dt>
              <dd>{formatPercent(state.data.adherence)}</dd>
            </div>
            <div>
              <dt>Bypass rate</dt>
              <dd>{formatPercent(state.data.bypass_rate)}</dd>
            </div>
            <div>
              <dt>Calibration</dt>
              <dd>{state.data.calibration === null ? '—' : state.data.calibration.toFixed(2)}</dd>
            </div>
            <div>
              <dt>Due</dt>
              <dd>{state.data.due_count}</dd>
            </div>
            {/* Retention (1d/7d/30d) is a per-person figure on this response
               (R3a: per-concept retention is still an open contract gap), so
               it lives in the summary, not repeated on every concept row. */}
            <div>
              <dt>Retention 1d/7d/30d</dt>
              <dd>
                {formatPercent(state.data.retention.d1.accuracy)} / {formatPercent(state.data.retention.d7.accuracy)} /{' '}
                {formatPercent(state.data.retention.d30.accuracy)}
              </dd>
            </div>
          </dl>

          <table className="team-drilldown-table" data-testid="team-drilldown-concepts">
            <thead>
              <tr>
                <th scope="col">Concept</th>
                <th scope="col">p(known)</th>
                <th scope="col">Mastered</th>
              </tr>
            </thead>
            <tbody>
              {state.data.concepts.map((entry) => {
                const band = pKnownBand(entry.p_known)
                return (
                  <tr key={entry.concept_id}>
                    <th scope="row">{conceptLabel(entry.concept_id, conceptTitles)}</th>
                    <td data-band={band.key}>{formatPercent(entry.p_known)}</td>
                    <td>{entry.mastered ? 'Yes' : 'No'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          <p className="team-privacy-note" data-testid="team-drilldown-privacy-note">
            Concept-level state only — never an answer, an item, or a transcript. Never shown here.
          </p>
        </>
      )}
    </div>
  )
}
