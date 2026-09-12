import raw from './hugo-idempotency-history.json'

/**
 * R3b (build-day/issues.md): the contract has no history/time-series
 * endpoint — every `/me/*` response is a point-in-time snapshot — so there
 * is nothing live for the dashboard's 30-day "what Kata believes you know"
 * line to read. This file is generated once from the seed's own
 * `docs/seed/3-history/reviews.jsonl` (`agents-everywhere-hackathon`, the
 * one fixed dataset this build day runs against) for Hugo's `idempotency`
 * concept specifically. It is a scenario-specific shortcut for this fixed
 * demo, not a generalized "the" mechanism a real (non-seeded) learner's
 * dashboard could draw the same chart from — that needs a real history
 * endpoint the contract doesn't have yet.
 */
export interface SeedReview {
  /** ISO 8601, UTC. */
  at: string
  bypassed: boolean
}

export interface SeedIdempotencyReview extends SeedReview {
  correct: boolean
  kind: string
}

interface HugoHistory {
  personHandle: string
  conceptSlug: string
  idempotencyReviews: SeedIdempotencyReview[]
  allReviews: SeedReview[]
}

export const HUGO_IDEMPOTENCY_HISTORY = raw as HugoHistory
