import { Lock } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DataState } from '@/components/DataState'
import { ProgressChart, type HistoryReview } from '@/components/progress/ProgressChart'
import { Card, CardContent } from '@/components/ui/card'
import { useApiQuery } from '@/hooks/useApiQuery'
import { conceptSlug } from '@/lib/ferry-scenario'
import { cn } from '@/lib/utils'

interface ConceptProgress {
  concept_id: string
  p_known: number
  mastered: boolean
  due_count: number
  unlocked: boolean
}

interface RetentionBand {
  accuracy: number | null
  samples: number
}

interface Retention {
  d1: RetentionBand
  d7: RetentionBand
  d30: RetentionBand
}

interface Summary {
  retention: Retention
  bypass_rate: number
  calibration: number
}

interface ProgressResponse {
  concepts: ConceptProgress[]
  summary: Summary
}

interface HistoryResponse {
  days: number
  reviews: HistoryReview[]
}

const CHART_DAYS = 30
const DEFAULT_CONCEPT_SLUG = 'idempotency'

function retentionText(band: RetentionBand): string {
  return band.accuracy === null ? '—' : `${Math.round(band.accuracy * 100)}%`
}

function Tile({ testId, label, value, caption, delta }: { testId: string; label: string; value: string; caption: string; delta?: string }) {
  return (
    <Card data-testid={testId}>
      <CardContent className="flex flex-col gap-1.5 pt-5">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
          {delta && <span className="rounded-full bg-kata-good-2 px-2 py-0.5 text-[11px] font-medium text-kata-good">{delta}</span>}
        </div>
        <p className="font-heading text-2xl font-semibold tabular-nums">{value}</p>
        <p className="text-xs text-muted-foreground">{caption}</p>
      </CardContent>
    </Card>
  )
}

function calibrationLabel(t: (k: string, opts?: Record<string, unknown>) => string, value: number): string {
  const signed = `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(2)}`
  if (value > 0.05) return t('progress.calibrationOver', { value: signed })
  if (value < -0.05) return t('progress.calibrationUnder', { value: signed })
  return t('progress.calibrationWellCalibrated', { value: signed })
}

export function Progress() {
  const { t } = useTranslation()
  const progress = useApiQuery<ProgressResponse>('progress', '/me/progress')
  const history = useApiQuery<HistoryResponse>('progress-history', `/me/history?days=${CHART_DAYS}`)
  const [selectedConceptId, setSelectedConceptId] = useState<string | null>(null)
  // react-query's own fetch timestamp — the chart's "updated" badge, no
  // separate state/effect needed to track it.
  const chartLoadedAt = history.dataUpdatedAt || Date.now()

  const repsByConcept = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of history.data?.reviews ?? []) {
      map.set(r.concept_id, (map.get(r.concept_id) ?? 0) + 1)
    }
    return map
  }, [history.data])

  const defaultConceptId = useMemo(() => {
    const concepts = progress.data?.concepts ?? []
    const bySlug = concepts.find((c) => conceptSlug(c.concept_id) === DEFAULT_CONCEPT_SLUG)
    return bySlug?.concept_id ?? concepts[0]?.concept_id ?? null
  }, [progress.data])

  const activeConceptId = selectedConceptId ?? defaultConceptId

  const conceptReviews = useMemo(
    () => (history.data?.reviews ?? []).filter((r) => r.concept_id === activeConceptId),
    [history.data, activeConceptId],
  )

  // The tile is labelled "· 30d" — compute it from the same 30-day
  // /me/history rows the chart uses, not `summary.bypass_rate` (all-time,
  // agency-v1 engine/analytics.py), which disagreed with its own label.
  const bypass30d = useMemo(() => {
    const reviews = history.data?.reviews ?? []
    if (reviews.length === 0) return null
    return reviews.filter((r) => r.bypassed).length / reviews.length
  }, [history.data])

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
      <DataState query={progress} screen={t('progress.title')} isEmpty={(d) => d.concepts.length === 0} emptyLabel={t('progress.emptyProgress')}>
        {(data) => {
          const masteredCount = data.concepts.filter((c) => c.mastered).length
          const retentionDelta = data.summary.retention.d7.accuracy !== null && data.summary.retention.d30.accuracy !== null
            ? Math.round((data.summary.retention.d7.accuracy - data.summary.retention.d30.accuracy) * 100)
            : null

          return (
            <>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Tile
                  testId="tile-retention"
                  label={t('progress.tileRetention')}
                  value={`1d ${retentionText(data.summary.retention.d1)} · 7d ${retentionText(data.summary.retention.d7)} · 30d ${retentionText(data.summary.retention.d30)}`}
                  caption={t('progress.tileRetentionCaption')}
                  delta={retentionDelta !== null ? t('progress.retentionDelta', { pts: retentionDelta }) : undefined}
                />
                <Tile
                  testId="tile-mastery"
                  label={t('progress.tileMastery')}
                  value={`${masteredCount} / ${data.concepts.length}`}
                  caption={t('progress.tileMasteryCaption')}
                />
                <Tile
                  testId="tile-calibration"
                  label={t('progress.tileCalibration')}
                  value={data.summary.calibration >= 0 ? `+${data.summary.calibration.toFixed(2)}` : data.summary.calibration.toFixed(2)}
                  caption={calibrationLabel(t, data.summary.calibration)}
                />
                <Tile
                  testId="tile-bypass"
                  label={t('progress.tileBypass')}
                  value={bypass30d === null ? '—' : `${Math.round(bypass30d * 100)}%`}
                  caption={t('progress.tileBypassCaption')}
                />
              </div>

              <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
                <Card>
                  <CardContent className="pt-5">
                    <DataState query={history} screen={t('progress.title')} isEmpty={() => false}>
                      {(h) =>
                        activeConceptId && (
                          <ProgressChart
                            allReviews={h.reviews}
                            conceptReviews={conceptReviews}
                            conceptId={activeConceptId}
                            days={h.days}
                            updatedAt={chartLoadedAt}
                          />
                        )
                      }
                    </DataState>
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="flex flex-col gap-3 pt-5">
                    <div className="flex items-center justify-between">
                      <h3 className="font-heading text-sm font-semibold">{t('progress.masteryPerConceptTitle')}</h3>
                      <span className="text-[11px] text-muted-foreground">{t('progress.basedOnReps')}</span>
                    </div>
                    <ul className="flex flex-col" data-testid="mastery-per-concept">
                      {data.concepts
                        .slice()
                        .sort((a, b) => b.p_known - a.p_known)
                        .map((c) => (
                          <li key={c.concept_id}>
                            <button
                              type="button"
                              data-testid={`mastery-row-${conceptSlug(c.concept_id)}`}
                              onClick={() => c.unlocked && setSelectedConceptId(c.concept_id)}
                              disabled={!c.unlocked}
                              className={cn(
                                'flex w-full items-center gap-2 border-b py-2 text-left text-xs last:border-b-0',
                                c.concept_id === activeConceptId && 'bg-secondary/50',
                                !c.unlocked && 'cursor-not-allowed opacity-60',
                              )}
                            >
                              <code className="w-32 shrink-0 truncate font-mono text-[11px]">{conceptSlug(c.concept_id)}</code>
                              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                                <span className="block h-full rounded-full bg-kata-teal" style={{ width: `${Math.round(c.p_known * 100)}%` }} />
                              </span>
                              <span className="w-9 shrink-0 text-right tabular-nums text-muted-foreground">{c.p_known.toFixed(2)}</span>
                              <span className="w-14 shrink-0 text-right text-muted-foreground">
                                {c.unlocked ? t('progress.repsCount', { count: repsByConcept.get(c.concept_id) ?? 0 }) : <Lock className="ml-auto size-3" />}
                              </span>
                            </button>
                          </li>
                        ))}
                    </ul>
                    <p className="text-[11px] text-muted-foreground">{t('progress.footNote')}</p>
                  </CardContent>
                </Card>
              </div>
            </>
          )
        }}
      </DataState>
    </div>
  )
}
