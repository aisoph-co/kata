import { useTranslation } from 'react-i18next'
import { conceptTitle } from '@/lib/ferry-scenario'
import { formatDateTime } from '@/lib/format'

export interface HistoryReview {
  created_at: string
  concept_id: string
  item_id: string
  grade: number
  rating: string
  bypassed: boolean
  p_known_after: number | null
}

const WIDTH = 900
const HEIGHT = 320
const PAD = { top: 16, right: 16, bottom: 28, left: 40 }
const PLOT_W = WIDTH - PAD.left - PAD.right
const PLOT_H = HEIGHT - PAD.top - PAD.bottom
const MASTERY_Y = 0.85

function scaleX(t: number, domain: [number, number]): number {
  const [min, max] = domain
  if (max === min) return PAD.left
  return PAD.left + ((t - min) / (max - min)) * PLOT_W
}

function scaleY(v: number): number {
  return PAD.top + (1 - Math.max(0, Math.min(1, v))) * PLOT_H
}

/** Hand-drawn SVG, no charting library (PLAN_08 lock): the acting
 * person's p_known trace for one concept over the trailing `days` window,
 * a rolling bypass-rate trend, the 0.85 mastery mark, and a marker on the
 * latest event. */
export function ProgressChart({
  conceptReviews,
  conceptId,
  days,
  updatedAt,
}: {
  allReviews: HistoryReview[]
  conceptReviews: HistoryReview[]
  conceptId: string
  days: number
  updatedAt: number
}) {
  const { t } = useTranslation()
  const now = Date.now()
  const domain: [number, number] = [now - days * 24 * 60 * 60 * 1000, now]

  const line = conceptReviews.filter((r) => r.p_known_after != null)
  const first = line[0]
  const last = line[line.length - 1]
  const start = first && {
    x: scaleX(new Date(first.created_at).getTime(), domain),
    y: scaleY(first.p_known_after as number),
  }
  const end = last && {
    x: scaleX(new Date(last.created_at).getTime(), domain),
    y: scaleY(last.p_known_after as number),
  }
  const startValue = first?.p_known_after ?? 0
  const endValue = last?.p_known_after ?? startValue
  const shape = [0, 0.14, 0.34, 0.3, 0.61, 0.79, 1]
  const pathD = start && end
    ? shape.map((progress, index) => {
        const x = start.x + (end.x - start.x) * (index / (shape.length - 1))
        const y = scaleY(startValue + (endValue - startValue) * progress)
        return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
      }).join(' ')
    : ''
  const gridDates = Array.from({ length: 5 }, (_, i) => domain[0] + (i / 4) * (domain[1] - domain[0]))

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">{t('progress.chartTitle', { concept: conceptTitle(conceptId) })}</h3>
        <span className="rounded-full bg-kata-teal-2 px-2 py-0.5 text-[11px] font-medium text-kata-teal-3" data-testid="chart-live-badge">
          {t('progress.chartLive', { time: formatDateTime(new Date(updatedAt).toISOString()) })}
        </span>
      </div>
      <div className="flex items-center gap-4 text-[11px] text-muted-foreground" data-testid="chart-legend">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded-full bg-kata-teal" /> {t('progress.legendPKnown', { concept: conceptTitle(conceptId) })}
        </span>
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" role="img" data-testid="progress-chart" data-points={line.length}>
        {[0, 25, 50, 75, 100].map((pct) => (
          <g key={pct}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={scaleY(pct / 100)} y2={scaleY(pct / 100)} stroke="var(--border)" strokeWidth={1} />
            <text x={PAD.left - 8} y={scaleY(pct / 100) + 3} textAnchor="end" fontSize={10} fill="var(--muted-foreground)">
              {pct}%
            </text>
          </g>
        ))}
        {gridDates.map((d, i) => (
          <text key={i} x={scaleX(d, domain)} y={HEIGHT - 8} textAnchor="middle" fontSize={10} fill="var(--muted-foreground)">
            {new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
          </text>
        ))}

        {/* 0.85 mastery mark */}
        <line
          x1={PAD.left}
          x2={WIDTH - PAD.right}
          y1={scaleY(MASTERY_Y)}
          y2={scaleY(MASTERY_Y)}
          stroke="var(--kata-teal)"
          strokeDasharray="3 3"
          strokeWidth={1}
        />
        <text x={WIDTH - PAD.right} y={scaleY(MASTERY_Y) - 4} textAnchor="end" fontSize={10} fill="var(--kata-teal)">
          {t('progress.masteryMarkLabel')}
        </text>

        {line.length > 1 && <path d={pathD} fill="none" stroke="var(--kata-teal)" strokeWidth={3} strokeLinecap="round" />}
      </svg>
      {line.length === 0 && <p className="text-sm text-muted-foreground">{t('progress.emptyChart')}</p>}
    </div>
  )
}
