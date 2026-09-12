import type { SeedIdempotencyReview, SeedReview } from '@/data/hugo-idempotency-history'

// Same constants the learning-service core's engine uses (BKT update),
// replayed here only to draw the R3b chart from the seed's own history
// file — never used to compute a tile or table value the core's real
// `/me/progress`/`/me/concept-graph` responses already provide.
const P_INIT = 0.2
const P_SLIP = 0.1
const P_TRANSIT = 0.15

function guessProbability(kind: string): number {
  return kind === 'mcq' ? 0.25 : 0.1
}

function bktUpdate(p: number, correct: boolean, kind: string): number {
  const g = guessProbability(kind)
  const posterior = correct ? (p * (1 - P_SLIP)) / (p * (1 - P_SLIP) + (1 - p) * g) : (p * P_SLIP) / (p * P_SLIP + (1 - p) * (1 - g))
  return posterior + (1 - posterior) * P_TRANSIT
}

export interface TracePoint {
  at: number
  pKnown: number
  bypassed: boolean
}

/** The concept's p_known after each review, in order. */
export function replayPKnown(reviews: SeedIdempotencyReview[]): TracePoint[] {
  let p = P_INIT
  return reviews.map((r) => {
    p = bktUpdate(p, r.correct, r.kind)
    return { at: new Date(r.at).getTime(), pKnown: p, bypassed: r.bypassed }
  })
}

export interface BypassPoint {
  at: number
  rate: number
}

/** Cumulative bypass rate up to and including each review — the same
 * statistic the bypass-rate tile reports, as a trend rather than a point
 * (flows.md "Happy path — personal dashboard"). */
export function cumulativeBypassRate(reviews: SeedReview[]): BypassPoint[] {
  let bypassed = 0
  return reviews.map((r, i) => {
    if (r.bypassed) bypassed += 1
    return { at: new Date(r.at).getTime(), rate: bypassed / (i + 1) }
  })
}

export function windowLast<T extends { at: number }>(points: T[], days: number, endAt: number): T[] {
  const start = endAt - days * 24 * 60 * 60 * 1000
  return points.filter((p) => p.at >= start && p.at <= endAt)
}
