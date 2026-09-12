import { useMemo } from 'react'
import { HUGO_IDEMPOTENCY_HISTORY } from '@/data/hugo-idempotency-history'
import { cumulativeBypassRate, replayPKnown, windowLast, type TracePoint } from '@/lib/bkt-replay'

const WIDTH = 720
const HEIGHT = 240
const PAD = { top: 12, right: 12, bottom: 24, left: 32 }
const PLOT_W = WIDTH - PAD.left - PAD.right
const PLOT_H = HEIGHT - PAD.top - PAD.bottom
const CHART_DAYS = 30
export const MASTERY_THRESHOLD = 0.85

function scaleX(at: number, domain: [number, number]): number {
  const [min, max] = domain
  if (max === min) return PAD.left
  return PAD.left + ((at - min) / (max - min)) * PLOT_W
}

function scaleY(v: number): number {
  return PAD.top + (1 - Math.max(0, Math.min(1, v))) * PLOT_H
}

function pathFor(points: { at: number; y: number }[], domain: [number, number]): string {
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'}${scaleX(p.at, domain).toFixed(1)},${p.y.toFixed(1)}`).join(' ')
}

/**
 * R3b's chart: the acting learner's `idempotency` p_known over the trailing
 * 30 days, the 0.85 mastery threshold, the bypass event and its
 * closing-question recovery, and the bypass-rate trend as a second series —
 * built from `HUGO_IDEMPOTENCY_HISTORY` (see that file's own doc comment
 * for why: no history endpoint on the contract yet).
 */
export function MasteryChart() {
  const { domain, pKnownPoints, thresholdLineY, bypassEvent, recoveryEvent, bypassRatePoints } = useMemo(() => {
    const idemTrace = replayPKnown(HUGO_IDEMPOTENCY_HISTORY.idempotencyReviews)
    const allTimestamps = HUGO_IDEMPOTENCY_HISTORY.allReviews.map((r) => new Date(r.at).getTime())
    const endAt = Math.max(...allTimestamps, ...idemTrace.map((p) => p.at))
    const windowed = windowLast(idemTrace, CHART_DAYS, endAt)
    const domain: [number, number] = [endAt - CHART_DAYS * 24 * 60 * 60 * 1000, endAt]

    // Flow 4b / verify_demo_beats.py: the beat is the bypass closest to the
    // end of the chart's window, and its recovery is the next non-bypassed
    // review of the same concept right after it.
    const bypassesInWindow = windowed.filter((p) => p.bypassed)
    const bypassEvent = bypassesInWindow[bypassesInWindow.length - 1] ?? null
    const recoveryEvent = bypassEvent ? (windowed.find((p) => p.at > bypassEvent.at && !p.bypassed) ?? null) : null

    const bypassRate = windowLast(cumulativeBypassRate(HUGO_IDEMPOTENCY_HISTORY.allReviews), CHART_DAYS, endAt)

    return {
      domain,
      pKnownPoints: windowed,
      thresholdLineY: scaleY(MASTERY_THRESHOLD),
      bypassEvent,
      recoveryEvent,
      bypassRatePoints: bypassRate,
    }
  }, [])

  const linePoints = pKnownPoints.map((p: TracePoint) => ({ at: p.at, y: scaleY(p.pKnown) }))
  const bypassSeriesPoints = bypassRatePoints.map((p) => ({ at: p.at, y: scaleY(p.rate) }))

  return (
    <div className="dashboard-chart" data-testid="dashboard-mastery-chart" data-concept={HUGO_IDEMPOTENCY_HISTORY.conceptSlug}>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="What Kata believes you know: idempotency">
        <line
          data-testid="mastery-threshold-line"
          data-value={MASTERY_THRESHOLD}
          x1={PAD.left}
          x2={WIDTH - PAD.right}
          y1={thresholdLineY}
          y2={thresholdLineY}
          stroke="var(--kata-teal, #22d3ee)"
          strokeDasharray="4 4"
        />

        {bypassSeriesPoints.length > 1 && (
          <path
            data-testid="bypass-rate-series"
            d={pathFor(bypassSeriesPoints, domain)}
            fill="none"
            stroke="var(--kata-warn, #fb923c)"
            strokeWidth={2}
            strokeDasharray="6 4"
          />
        )}

        {linePoints.length > 1 && <path d={pathFor(linePoints, domain)} fill="none" stroke="var(--kata-teal, #22d3ee)" strokeWidth={2.5} />}

        {bypassEvent && (
          <circle
            data-testid="bypass-event-annotation"
            cx={scaleX(bypassEvent.at, domain)}
            cy={scaleY(bypassEvent.pKnown)}
            r={5}
            fill="var(--kata-warn, #fb923c)"
          />
        )}
        {recoveryEvent && (
          <circle
            data-testid="closing-question-recovery-annotation"
            cx={scaleX(recoveryEvent.at, domain)}
            cy={scaleY(recoveryEvent.pKnown)}
            r={6}
            fill="none"
            stroke="var(--kata-good, #4ade80)"
            strokeWidth={2}
          />
        )}
      </svg>
    </div>
  )
}
