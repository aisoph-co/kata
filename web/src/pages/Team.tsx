import { useQueries } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DataState } from '@/components/DataState'
import { PersonDrillPanel } from '@/components/PersonDrillPanel'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useApiQuery } from '@/hooks/useApiQuery'
import { apiFetch } from '@/lib/api-client'
import { conceptSlug, conceptTitle, personName } from '@/lib/ferry-scenario'
import { usePersona } from '@/lib/persona-store'
import { cn } from '@/lib/utils'

interface TeamOverview {
  concepts: { concept_id: string; mean_mastery: number; share_mastered: number; at_risk_count: number }[]
  people: { person_id: string; adherence: number; velocity: number; last_active: string | null }[]
}

interface TeamConceptDetail {
  concept_id: string
  people: { person_id: string; p_known: number; mastered: boolean }[]
}

interface TeamAuditEntry {
  id: string
  actor_person_id: string
  subject_scope: string
  endpoint: string
  at: string
}

interface TeamPersonCalibration {
  calibration: number | null
}

function formatSigned(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

const BANDS = [
  { max: 0.25, className: 'bg-kata-heat-1' },
  { max: 0.5, className: 'bg-kata-heat-2' },
  { max: 0.7, className: 'bg-kata-heat-3' },
  { max: 0.85, className: 'bg-kata-heat-4' },
  { max: Infinity, className: 'bg-kata-heat-5' },
] as const

function heatClass(p: number): string {
  return BANDS.find((b) => p < b.max)?.className ?? BANDS[BANDS.length - 1].className
}

function HeatCell({ p }: { p: number }) {
  // Band off the same value the cell displays, not the raw p_known — a
  // value like 0.249 rounds to the "0.25" text but must not paint the
  // 0.25-0.5 band, or the shown number and its colour disagree.
  const displayed = Number(p.toFixed(2))
  return (
    <span
      className={cn('flex size-11 items-center justify-center rounded font-mono text-[11px] font-medium text-foreground/80', heatClass(displayed))}
      data-testid="heatmap-cell"
    >
      {displayed.toFixed(2)}
    </span>
  )
}

/** Static, honest read of the real `/team/overview` + per-concept detail —
 * the four insights the mock's "What the manager gets" card shows, minus
 * "How it was built" (PLAN_08: dropped, it described the eval build, not
 * this data). */
function ManagerGetsCard({
  overview,
  conceptDetails,
  peopleCount,
  actorName,
  auditEntry,
}: {
  overview: TeamOverview
  conceptDetails: (TeamConceptDetail | undefined)[]
  peopleCount: number
  actorName: string
  auditEntry?: TeamAuditEntry
}) {
  const { t } = useTranslation()

  const lowestMeanConcept = overview.concepts.length
    ? overview.concepts.reduce((min, c) => (c.mean_mastery < min.mean_mastery ? c : min))
    : null
  const lowestAdherencePerson = overview.people.length
    ? overview.people.reduce((min, p) => (p.adherence < min.adherence ? p : min))
    : null

  const bestGap = useMemo(() => {
    const meanByConcept = new Map(overview.concepts.map((c) => [c.concept_id, c.mean_mastery]))
    const bestByPerson = new Map<string, { conceptId: string; value: number }>()
    for (const detail of conceptDetails) {
      if (!detail) continue
      for (const cell of detail.people) {
        const current = bestByPerson.get(cell.person_id)
        if (!current || cell.p_known > current.value) {
          bestByPerson.set(cell.person_id, { conceptId: detail.concept_id, value: cell.p_known })
        }
      }
    }
    let best: { personId: string; conceptId: string; value: number; mean: number; gap: number } | null = null
    for (const [personId, entry] of bestByPerson) {
      const mean = meanByConcept.get(entry.conceptId) ?? 0
      const gap = entry.value - mean
      if (!best || gap > best.gap) best = { personId, conceptId: entry.conceptId, value: entry.value, mean, gap }
    }
    return best
  }, [overview.concepts, conceptDetails])

  // The rest of the concepts this same person holds, so the note reads "near
  // zero on the rest" with a real number rather than just naming their one
  // strong concept.
  const restMean = useMemo(() => {
    if (!bestGap) return null
    const values = conceptDetails.flatMap((d) =>
      !d || d.concept_id === bestGap.conceptId
        ? []
        : d.people.filter((p) => p.person_id === bestGap.personId).map((p) => p.p_known),
    )
    return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null
  }, [conceptDetails, bestGap])

  // Concept-level only, per this screen's privacy test — no answer or item
  // field, just the calibration scalar already exposed on the person's own
  // `/team/people/{id}` summary (R3).
  const calibration = useApiQuery<TeamPersonCalibration>(
    bestGap ? `team-person-calibration-${bestGap.personId}` : 'team-person-calibration-none',
    bestGap ? `/team/people/${bestGap.personId}` : '',
    { enabled: !!bestGap },
  )

  // "rendered from GET /team/audit" (spec): this manager's own most recent
  // read of this exact screen, not a client-side guess — falls back to
  // "now" only while that fetch is still pending or unavailable (audit log
  // access is operator-only; not every manager can see it, though every
  // manager's read is still recorded).
  const fallbackAt = useMemo(() => new Date().toISOString(), [])
  const auditAt = auditEntry?.at ?? fallbackAt
  const auditEndpoint = auditEntry?.endpoint ?? '/team/overview'

  return (
    <Card data-testid="manager-gets-card">
      <CardHeader>
        <CardTitle className="text-base">{t('team.managerGetsTitle')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        {lowestMeanConcept && (
          <div data-testid="manager-gets-team-gap">
            <p className="font-medium">{t('team.teamGapLabel')}</p>
            <p className="text-muted-foreground">
              {t('team.teamGapBody', {
                concept: conceptSlug(lowestMeanConcept.concept_id),
                mean: lowestMeanConcept.mean_mastery.toFixed(2),
                mastered: Math.round(lowestMeanConcept.share_mastered * peopleCount),
                total: peopleCount,
              })}
            </p>
          </div>
        )}
        {lowestAdherencePerson && (
          <div data-testid="manager-gets-adherence">
            <p className="font-medium">{t('team.lowestAdherenceLabel')}</p>
            <p className="text-muted-foreground">
              {t('team.lowestAdherenceBody', {
                name: personName(lowestAdherencePerson.person_id),
                pct: Math.round(lowestAdherencePerson.adherence * 100),
              })}
            </p>
          </div>
        )}
        {bestGap && (
          <div data-testid="manager-gets-top-gap">
            <p className="font-medium">{t('team.topGapLabel')}</p>
            <p className="text-muted-foreground">
              {t('team.topGapBody', {
                name: personName(bestGap.personId),
                concept: conceptSlug(bestGap.conceptId),
                value: bestGap.value.toFixed(2),
                restMean: restMean !== null ? restMean.toFixed(2) : '—',
                calibration: formatSigned(calibration.data?.calibration),
              })}
            </p>
          </div>
        )}
        <p className="text-xs text-muted-foreground">{t('team.privacyNote')}</p>
        <code className="rounded bg-muted px-2 py-1.5 font-mono text-[11px] text-muted-foreground" data-testid="manager-gets-audit">
          {t('team.auditLine', { at: auditAt, actor: actorName.toLowerCase(), endpoint: auditEndpoint, scope: peopleCount })}
        </code>
      </CardContent>
    </Card>
  )
}

export function Team() {
  const { t } = useTranslation()
  const persona = usePersona()
  // W10 (KATA-13): row click opens the drill-down as an in-page side panel
  // rather than navigating away from the heatmap; `openToken` forces a
  // fresh audit re-read on every open, even a re-click of the same row.
  const [drillPersonId, setDrillPersonId] = useState<string | null>(null)
  const [openToken, setOpenToken] = useState(0)
  const openDrill = (personId: string) => {
    setDrillPersonId(personId)
    setOpenToken((n) => n + 1)
  }
  const overview = useApiQuery<TeamOverview>('team-overview', '/team/overview')
  const conceptIds = overview.data?.concepts.map((c) => c.concept_id) ?? []
  const conceptQueries = useQueries({
    queries: conceptIds.map((id) => ({
      queryKey: ['team-concept', persona.id, id],
      queryFn: () => apiFetch<TeamConceptDetail>(`/team/concepts/${id}`, { persona }),
      enabled: overview.isSuccess,
      retry: false,
    })),
  })
  // 403s for a manager who isn't also an operator (`GET /team/audit` is
  // operator-only) — the side panel's audit line falls back to a local
  // timestamp in that case rather than blanking the screen.
  const audit = useApiQuery<{ entries: TeamAuditEntry[] }>('team-audit', '/team/audit', { enabled: overview.isSuccess })
  const overviewAuditEntry = audit.data?.entries.find(
    (e) => e.endpoint === '/team/overview' && e.actor_person_id === persona.personId,
  )

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6 px-6 py-8">
      <DataState query={overview} screen={t('team.title')} isEmpty={(d) => d.people.length === 0} emptyLabel={t('team.emptyReports')}>
        {(overviewData) => {
          const loadingConcepts = conceptQueries.some((q) => q.isLoading)
          const meanByConcept = new Map(overviewData.concepts.map((c) => [c.concept_id, c.mean_mastery]))

          return (
            <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
              <Card>
                <CardHeader className="flex flex-row flex-wrap items-center gap-2">
                  <CardTitle className="text-base">{t('team.title')}</CardTitle>
                  <Badge variant="secondary" data-testid="team-badge-concept-level">
                    {t('team.badgeConceptLevel')}
                  </Badge>
                  <Badge variant="outline" data-testid="team-badge-audited">
                    {t('team.badgeAudited')}
                  </Badge>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    {loadingConcepts ? (
                      <Skeleton className="h-64 w-full" />
                    ) : (
                      <table className="border-separate border-spacing-1" data-testid="team-heatmap">
                        <thead>
                          <tr className="h-36">
                            <th className="text-left align-bottom text-xs text-muted-foreground">{t('team.colPerson')}</th>
                            {conceptIds.map((id) => (
                              <th key={id} className="relative w-11 align-bottom">
                                <div className="relative h-32 w-11">
                                  <span
                                    className="absolute bottom-1 left-4 origin-bottom-left -rotate-45 whitespace-nowrap font-mono text-[10px] text-muted-foreground"
                                    title={conceptTitle(id)}
                                  >
                                    {conceptSlug(id)}
                                  </span>
                                </div>
                              </th>
                            ))}
                            <th className="px-1 align-bottom text-xs text-muted-foreground">{t('team.colAdherence')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {overviewData.people.map((p) => (
                            <tr key={p.person_id}>
                              <td className="whitespace-nowrap pr-3 text-sm">
                                <button
                                  type="button"
                                  onClick={() => openDrill(p.person_id)}
                                  className="hover:underline"
                                  data-testid={`team-person-${p.person_id}`}
                                >
                                  {personName(p.person_id)}
                                </button>
                              </td>
                              {conceptQueries.map((q, i) => {
                                const cell = (q.data?.people ?? []).find((c) => c.person_id === p.person_id)
                                return (
                                  <td key={conceptIds[i]}>
                                    {cell ? (
                                      <HeatCell p={cell.p_known} />
                                    ) : q.isError ? (
                                      <span
                                        className="flex size-11 items-center justify-center rounded bg-muted text-muted-foreground"
                                        data-testid="heatmap-cell-error"
                                      >
                                        —
                                      </span>
                                    ) : (
                                      <Skeleton className="size-11" />
                                    )}
                                  </td>
                                )
                              })}
                              <td className="px-1 text-center text-sm tabular-nums">{Math.round(p.adherence * 100)}%</td>
                            </tr>
                          ))}
                          <tr className="border-t" data-testid="team-mean-row">
                            <td className="pr-3 pt-2 text-sm font-medium">{t('team.teamMeanRow')}</td>
                            {conceptIds.map((id) => (
                              <td key={id} className="pt-2 text-center font-mono text-xs tabular-nums text-muted-foreground">
                                {(meanByConcept.get(id) ?? 0).toFixed(2)}
                              </td>
                            ))}
                            <td className="pt-2" />
                          </tr>
                        </tbody>
                      </table>
                    )}
                  </div>

                  <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-muted-foreground" data-testid="heatmap-legend">
                    <span className="font-medium text-foreground">p_known</span>
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block size-3 rounded bg-kata-heat-1" /> {t('team.legendBand1')}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block size-3 rounded bg-kata-heat-2" /> {t('team.legendBand2')}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block size-3 rounded bg-kata-heat-3" /> {t('team.legendBand3')}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block size-3 rounded bg-kata-heat-4" /> {t('team.legendBand4')}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block size-3 rounded bg-kata-heat-5" /> {t('team.legendBand5')}
                    </span>
                  </div>
                </CardContent>
              </Card>

              <ManagerGetsCard
                overview={overviewData}
                conceptDetails={conceptQueries.map((q) => q.data)}
                peopleCount={overviewData.people.length}
                actorName={persona.name}
                auditEntry={overviewAuditEntry}
              />
            </div>
          )
        }}
      </DataState>
      <PersonDrillPanel
        personId={drillPersonId}
        openToken={openToken}
        onOpenChange={(open) => {
          if (!open) setDrillPersonId(null)
        }}
      />
    </div>
  )
}
