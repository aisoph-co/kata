import { useEffect, useMemo, useState } from 'react'
import { useConceptTitles } from '@/hooks/useConceptTitles'
import { useTeamAudit } from '@/hooks/useTeamAudit'
import { useTeamHeatmapMatrix } from '@/hooks/useTeamHeatmapMatrix'
import { useTeamOverview } from '@/hooks/useTeamOverview'
import { useTeamPersonDetail } from '@/hooks/useTeamPersonDetail'
import { ApiError } from '@/lib/api-client'
import { pKnownBand } from '@/lib/p-known-bands'
import { goneQuiet, pmAsymmetry, teamGap } from '@/lib/team-callouts'
import { conceptLabel, formatPercent, personLabel } from '@/lib/team-format'
import { useWebSession } from '@/lib/session-store'
import { TeamPersonDrilldown } from '@/pages/TeamPersonDrilldown'
import { TeamSidePanel } from '@/pages/TeamSidePanel'
import '@/pages/team-view.css'

/**
 * Frame 11 (`build-day/SCREENS.md`): the manager team heatmap and its
 * click-through drill-down (issue KATA-8/W4). Built against the frozen
 * `/team/*` contract shape (`contracts/openapi.yaml`) — the backend that
 * serves it is C2/KATA-3's own issue, landing separately.
 */
export function TeamView() {
  const session = useWebSession()
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(null)
  const [auditRefreshKey, setAuditRefreshKey] = useState(0)

  const header = session?.header ?? ''
  const overview = useTeamOverview(header)
  const conceptIds = useMemo(() => overview.data?.concepts.map((c) => c.concept_id) ?? [], [overview.data])
  const matrix = useTeamHeatmapMatrix(header, conceptIds)
  const conceptTitles = useConceptTitles(header)
  const audit = useTeamAudit(header, auditRefreshKey)
  const detail = useTeamPersonDetail(header, selectedPersonId)

  const gap = useMemo(() => (overview.data ? teamGap(overview.data.concepts) : null), [overview.data])
  const quiet = useMemo(() => (overview.data ? goneQuiet(overview.data.people) : null), [overview.data])
  const asymmetry = useMemo(() => pmAsymmetry(matrix.matrix, conceptIds), [matrix.matrix, conceptIds])

  function openPerson(personId: string) {
    setSelectedPersonId(personId)
  }

  // The audit row for this drill-down is written by the server as part of
  // handling `GET /team/people/{id}` itself — bumping the refresh key at
  // the same time `openPerson` fires would race `useTeamAudit`'s read
  // against that write (both effects fire off the same click; nothing
  // orders one before the other). Keying off `detail.data` instead only
  // fires once `/team/people/{id}` has actually resolved, so the new row
  // is guaranteed to exist by the time `/team/audit` is re-read. Never
  // fires on a failed detail fetch (`detail.data` stays null), since a
  // request that never reached the person shouldn't be assumed to have
  // written a row.
  useEffect(() => {
    if (selectedPersonId && detail.data && detail.data.person_id === selectedPersonId) {
      setAuditRefreshKey((key) => key + 1)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.data])

  if (!session) return null

  if (overview.isError) {
    const isOutsideAccess = overview.error instanceof ApiError && overview.error.status === 403
    return (
      <div className="team-view" data-testid="team-view-forbidden">
        <p>
          {isOutsideAccess
            ? "You don't manage a team, so there's no team view to show."
            : "Couldn't load the team view."}
        </p>
      </div>
    )
  }

  if (overview.isPending || matrix.isPending) {
    return (
      <div className="team-view" data-testid="team-view-loading">
        <p>Loading team view…</p>
      </div>
    )
  }

  const people = overview.data?.people ?? []
  const concepts = overview.data?.concepts ?? []

  return (
    <div className="team-view" data-testid="team-view">
      <header className="team-view-header">
        <h2>Team</h2>
        <span className="team-badge" data-testid="team-badge-concept-level">
          concept-level only
        </span>
        <span className="team-badge" data-testid="team-badge-audited">
          this read is audited
        </span>
      </header>

      <table className="team-heatmap" data-testid="team-heatmap">
        <thead>
          <tr>
            <th scope="col">Person</th>
            {concepts.map((concept) => (
              <th scope="col" key={concept.concept_id}>
                {conceptLabel(concept.concept_id, conceptTitles)}
              </th>
            ))}
            <th scope="col">Adherence</th>
          </tr>
        </thead>
        <tbody>
          {people.map((person) => (
            <tr key={person.person_id}>
              <th scope="row">
                <button
                  className="team-heatmap-row-button"
                  data-testid={`team-row-${person.person_id}`}
                  onClick={() => openPerson(person.person_id)}
                >
                  {personLabel(person.person_id)}
                </button>
              </th>
              {concepts.map((concept) => {
                const cell = matrix.matrix[person.person_id]?.[concept.concept_id]
                if (!cell) {
                  return (
                    <td key={concept.concept_id} data-testid="heatmap-cell-empty">
                      no reps yet
                    </td>
                  )
                }
                const band = pKnownBand(cell.p_known)
                return (
                  <td key={concept.concept_id} data-testid="heatmap-cell" data-band={band.key}>
                    {formatPercent(cell.p_known)}
                  </td>
                )
              })}
              <td data-testid={`team-adherence-${person.person_id}`}>{formatPercent(person.adherence)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr data-testid="team-mean-row">
            <th scope="row">Team mean</th>
            {concepts.map((concept) => {
              const band = pKnownBand(concept.mean_mastery)
              return (
                <td key={concept.concept_id} data-band={band.key}>
                  {formatPercent(concept.mean_mastery)}
                </td>
              )
            })}
            <td />
          </tr>
        </tfoot>
      </table>

      <TeamSidePanel
        gap={gap}
        quiet={quiet}
        asymmetry={asymmetry}
        auditEntries={audit.data?.entries ?? []}
        auditIsPending={audit.isPending}
        conceptTitles={conceptTitles}
      />

      {selectedPersonId && (
        <TeamPersonDrilldown
          personId={selectedPersonId}
          state={detail}
          conceptTitles={conceptTitles}
          onClose={() => setSelectedPersonId(null)}
        />
      )}
    </div>
  )
}
