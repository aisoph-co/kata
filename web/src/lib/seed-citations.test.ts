import { describe, expect, it } from 'vitest'
import { resolveCitationExcerpt, slugifyHeading } from './seed-citations'

describe('slugifyHeading', () => {
  // Each pair is a real `1-context/` heading next to the real
  // `Topic.grounded_in` anchor it must resolve (`docs/seed/2-curriculum/topics.json`)
  // — GitHub's own slug rule, not an approximation.
  it.each([
    ['Sprint 42 — "stop double-charging" (current, 1–12 September)', 'sprint-42--stop-double-charging-current-112-september'],
    ['`psp-connectors/adyen/decline.go` — the nine-day silent failure', 'psp-connectorsadyendeclinego--the-nine-day-silent-failure'],
    ['The live situation (what the team is working on right now)', 'the-live-situation-what-the-team-is-working-on-right-now'],
    ['Reverted', 'reverted'],
    ['2026-08-22 · `checkout-api` v5.1.0', '2026-08-22--checkout-api-v510'],
  ])('slugifies %j to %j', (heading, slug) => {
    expect(slugifyHeading(heading)).toBe(slug)
  })
})

describe('resolveCitationExcerpt', () => {
  it('resolves an issue key against issues.jsonl', () => {
    const excerpt = resolveCitationExcerpt('PAY-1847')
    expect(excerpt).not.toBeNull()
    expect(excerpt?.sourceFile).toBe('issues.jsonl')
    expect(excerpt?.heading).toContain('PAY-1847')
    expect(excerpt?.text).toContain('Key is now taken from the payment intent')
  })

  it('resolves a file#anchor citation against the matching heading', () => {
    const excerpt = resolveCitationExcerpt('release-notes.md#reverted')
    expect(excerpt).not.toBeNull()
    expect(excerpt?.sourceFile).toBe('release-notes.md')
    expect(excerpt?.heading).toBe('Reverted')
  })

  it('resolves every citation the seeded topics actually use', () => {
    // docs/seed/2-curriculum/topics.json topic "idempotent-retries".grounded_in
    const citations = [
      'PAY-1841',
      'PAY-1847',
      'PAY-1852',
      'PAY-1859',
      'PAY-1872',
      'sprint-history.md#sprint-42--stop-double-charging-current-112-september',
    ]
    for (const citation of citations) {
      expect(resolveCitationExcerpt(citation), citation).not.toBeNull()
    }
  })

  it('returns null, not a fabricated excerpt, for an unknown citation', () => {
    expect(resolveCitationExcerpt('PAY-9999')).toBeNull()
    expect(resolveCitationExcerpt('company.md#no-such-heading')).toBeNull()
  })
})
