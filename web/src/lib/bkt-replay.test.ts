import { describe, expect, it } from 'vitest'
import { cumulativeBypassRate, replayPKnown, windowLast } from './bkt-replay'
import type { SeedIdempotencyReview, SeedReview } from '@/data/hugo-idempotency-history'

function review(at: string, correct: boolean, kind = 'mcq', bypassed = false): SeedIdempotencyReview {
  return { at, correct, kind, bypassed }
}

describe('replayPKnown', () => {
  it('matches the core engine\'s BKT update (P_INIT 0.20, p_guess 0.25 mcq, p_slip 0.10, p_transit 0.15)', () => {
    const [first] = replayPKnown([review('2026-01-01T00:00:00Z', true)])
    // posterior = 0.2*0.9 / (0.2*0.9 + 0.8*0.25) = 0.18/0.38; p = posterior + (1-posterior)*0.15
    expect(first.pKnown).toBeCloseTo(0.55263, 4)
  })

  it('climbs toward mastery on a run of correct answers', () => {
    const reviews = Array.from({ length: 10 }, (_, i) => review(`2026-01-0${(i % 9) + 1}T00:00:00Z`, true))
    const trace = replayPKnown(reviews)
    expect(trace[trace.length - 1].pKnown).toBeGreaterThan(trace[0].pKnown)
    expect(trace[trace.length - 1].pKnown).toBeGreaterThan(0.85)
  })

  it('a wrong answer pulls p_known down relative to the prior point', () => {
    const trace = replayPKnown([review('2026-01-01T00:00:00Z', true), review('2026-01-02T00:00:00Z', false)])
    expect(trace[1].pKnown).toBeLessThan(trace[0].pKnown)
  })

  it('carries the bypassed flag through onto the trace point for chart annotations', () => {
    const trace = replayPKnown([review('2026-01-01T00:00:00Z', false, 'mcq', true)])
    expect(trace[0].bypassed).toBe(true)
  })
})

describe('cumulativeBypassRate', () => {
  it('is the running share of reviews bypassed so far, not a trailing window', () => {
    const reviews: SeedReview[] = [
      { at: '2026-01-01T00:00:00Z', bypassed: false },
      { at: '2026-01-02T00:00:00Z', bypassed: true },
      { at: '2026-01-03T00:00:00Z', bypassed: false },
      { at: '2026-01-04T00:00:00Z', bypassed: true },
    ]
    const rates = cumulativeBypassRate(reviews)
    expect(rates.map((r) => r.rate)).toEqual([0, 0.5, 1 / 3, 0.5])
  })
})

describe('windowLast', () => {
  it('keeps only points within the trailing N days of the given end time', () => {
    const endAt = new Date('2026-02-01T00:00:00Z').getTime()
    const points = [
      { at: new Date('2026-01-01T00:00:00Z').getTime() }, // 31 days back — outside a 30-day window
      { at: new Date('2026-01-05T00:00:00Z').getTime() }, // inside
      { at: endAt }, // the boundary itself
    ]
    expect(windowLast(points, 30, endAt)).toHaveLength(2)
  })
})
