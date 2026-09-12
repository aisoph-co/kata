import type { ConceptTitle } from '@/hooks/useConceptTitles'
import type { GoneQuiet, PmAsymmetry, TeamGap } from '@/lib/team-callouts'
import type { AuditEntry } from '@/lib/team-types'
import { conceptLabel, formatPercent, formatTimestamp, personLabel } from '@/lib/team-format'

function latestEntry(entries: readonly AuditEntry[]): AuditEntry | null {
  if (entries.length === 0) return null
  return [...entries].sort((a, b) => (a.at < b.at ? 1 : -1))[0]
}

/**
 * The heatmap's side panel (issue: "team gap … 'gone quiet' … the
 * PM-asymmetry note … and the audit line itself"). Every call-out here is
 * derived client-side from `TeamOverviewResponse`/the assembled heatmap
 * matrix — no field on this panel is ever an answer, an item, or a
 * transcript (core spec, Testing).
 */
export function TeamSidePanel({
  gap,
  quiet,
  asymmetry,
  auditEntries,
  auditIsPending,
  conceptTitles,
}: {
  gap: TeamGap | null
  quiet: GoneQuiet | null
  asymmetry: PmAsymmetry | null
  auditEntries: readonly AuditEntry[]
  auditIsPending: boolean
  conceptTitles: Record<string, ConceptTitle>
}) {
  const latest = latestEntry(auditEntries)

  return (
    <aside className="team-side-panel" data-testid="team-side-panel">
      <section data-testid="team-gap-callout">
        <h4>Team gap</h4>
        {gap ? (
          <p>
            {conceptLabel(gap.conceptId, conceptTitles)} — {formatPercent(gap.meanMastery)} mean mastery,{' '}
            {formatPercent(gap.shareMastered)} of the subtree mastered.
          </p>
        ) : (
          <p>No reps yet.</p>
        )}
      </section>

      <section data-testid="team-gone-quiet-callout">
        <h4>Gone quiet</h4>
        {quiet ? (
          <p>
            {personLabel(quiet.personId)} — {formatPercent(quiet.adherence)} adherence.
          </p>
        ) : (
          <p>No reps yet.</p>
        )}
      </section>

      <section data-testid="team-pm-asymmetry-callout">
        <h4>PM asymmetry</h4>
        {asymmetry ? (
          <p>
            {personLabel(asymmetry.personId)} is at {formatPercent(asymmetry.pKnown)} on{' '}
            {conceptLabel(asymmetry.conceptId, conceptTitles)} and {formatPercent(asymmetry.restMean)} on average
            elsewhere — its calibration gap is visible in that person&rsquo;s own drill-down.
          </p>
        ) : (
          <p>No single-concept expert stands out yet.</p>
        )}
      </section>

      <p className="team-privacy-note" data-testid="team-side-panel-privacy-note">
        Concept-level only — no item text, no answer text, no transcript. Never shown here.
      </p>

      <section data-testid="team-audit-line">
        <h4>Audit</h4>
        {auditIsPending && !latest ? (
          <p>Loading…</p>
        ) : latest ? (
          <p>
            {formatTimestamp(latest.at)} · {personLabel(latest.actor_person_id)} · {latest.endpoint} · {latest.subject_scope}
          </p>
        ) : (
          <p>No reads recorded yet.</p>
        )}
      </section>
    </aside>
  )
}
