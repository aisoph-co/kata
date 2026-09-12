import { useTranslation } from 'react-i18next'
import { DataState } from '@/components/DataState'
import { MasteryBar } from '@/components/MasteryBar'
import { Badge } from '@/components/ui/badge'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useApiQuery } from '@/hooks/useApiQuery'
import { conceptTitle, personName } from '@/lib/ferry-scenario'
import { formatDateTime } from '@/lib/format'
import { usePersona } from '@/lib/persona-store'

interface PersonDetail {
  person_id: string
  concepts: { concept_id: string; p_known: number; mastered: boolean; due_count: number; unlocked: boolean }[]
  adherence: number
  velocity: number
  due_count: number
  last_active: string | null
}

interface TeamAuditEntry {
  id: string
  actor_person_id: string
  subject_scope: string
  endpoint: string
  at: string
}

/** KATA-13/W10: the row-click drill-down on top of W6's heatmap (frame 11,
 * no dedicated mock of its own) — a side panel with one person's own
 * concept-level state, sourced from the same `/team/people/{id}` the direct
 * link (`PersonDrilldown`) uses, so it carries the identical privacy
 * guarantee: p_known/mastered/due/unlocked only, never an item, answer, or
 * transcript field.
 *
 * The audit query only fires once the detail read resolves (`enabled` gated
 * on `detail.isSuccess`) and is keyed per-open, so it can't race the audit
 * row that read itself just wrote — the line shown here is this drill-down's
 * own entry, not a stale one from the parent screen's `/team/overview` load. */
export function PersonDrillPanel({
  personId,
  openToken,
  onOpenChange,
}: {
  personId: string | null
  /** Bumped by the caller on every click, even a re-click of the same row,
   * so the audit re-read below is never served the previous open's cache. */
  openToken: number
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const persona = usePersona()
  const detail = useApiQuery<PersonDetail>(`person-panel-${personId}-${openToken}`, personId ? `/team/people/${personId}` : '', {
    enabled: personId != null,
  })
  const audit = useApiQuery<{ entries: TeamAuditEntry[] }>(`team-audit-panel-${personId}-${openToken}`, '/team/audit', {
    enabled: personId != null && detail.isSuccess,
  })
  const auditEntry = audit.data?.entries.find(
    (e) => e.actor_person_id === persona.personId && e.subject_scope === `person:${personId}`,
  )
  // `/team/audit` is operator-only (spec) — same honest fallback as the
  // heatmap's own audit line: a local timestamp, never a blank line, for a
  // manager who can't read the audit log back.
  const fallbackAt = new Date().toISOString()

  return (
    <Sheet open={personId != null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-lg" data-testid="person-drill-panel">
        {personId != null && (
          <>
            <SheetHeader>
              <SheetTitle>{t('personDrilldown.titlePrefix', { name: personName(personId) })}</SheetTitle>
              <SheetDescription>{t('personDrilldown.description')}</SheetDescription>
            </SheetHeader>
            <div className="flex flex-col gap-4 overflow-y-auto px-4 pb-6">
              <DataState
                query={detail}
                screen={t('team.title')}
                isEmpty={(d) => d.concepts.length === 0}
                emptyLabel={t('personDrilldown.emptyConcepts')}
              >
                {(d) => (
                  <>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary">{t('personDrilldown.adherenceBadge', { pct: Math.round(d.adherence * 100) })}</Badge>
                      <Badge variant="outline">{t('personDrilldown.velocityBadge', { count: d.velocity })}</Badge>
                      <Badge variant="outline">{t('personDrilldown.dueBadge', { count: d.due_count })}</Badge>
                      <Badge variant="outline">{t('personDrilldown.lastActiveBadge', { date: formatDateTime(d.last_active) })}</Badge>
                    </div>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>{t('personDrilldown.colConcept')}</TableHead>
                          <TableHead>{t('personDrilldown.colPKnown')}</TableHead>
                          <TableHead>{t('personDrilldown.colMastered')}</TableHead>
                          <TableHead>{t('personDrilldown.colDue')}</TableHead>
                          <TableHead>{t('personDrilldown.colUnlocked')}</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {d.concepts.map((c) => (
                          <TableRow key={c.concept_id}>
                            <TableCell className="font-medium">{conceptTitle(c.concept_id)}</TableCell>
                            <TableCell className="w-40">
                              <MasteryBar p={c.p_known} />
                            </TableCell>
                            <TableCell>{c.mastered ? t('personDrilldown.yes') : t('personDrilldown.no')}</TableCell>
                            <TableCell>{c.due_count}</TableCell>
                            <TableCell>{c.unlocked ? t('personDrilldown.yes') : t('personDrilldown.no')}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    <code
                      className="rounded bg-muted px-2 py-1.5 font-mono text-[11px] text-muted-foreground"
                      data-testid="person-panel-audit"
                    >
                      {t('personDrilldown.auditLine', {
                        at: auditEntry?.at ?? fallbackAt,
                        actor: persona.name.toLowerCase(),
                        endpoint: auditEntry?.endpoint ?? `/team/people/${personId}`,
                      })}
                    </code>
                  </>
                )}
              </DataState>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
