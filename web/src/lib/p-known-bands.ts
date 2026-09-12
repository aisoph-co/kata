export type PKnownBandKey = 'unseen' | 'emerging' | 'developing' | 'approaching' | 'mastered'

export interface PKnownBand {
  key: PKnownBandKey
  label: string
}

/**
 * Five bands over `p_known` (spec: "five `p_known` bands", frame 11). The
 * top edge mirrors `curriculum.DEFAULT_MASTERY_THRESHOLD` (0.85) — the
 * common case, not a per-concept guarantee, since `TeamConceptDetailResponse`
 * carries each person's `mastered` boolean (computed server-side against
 * that concept's own threshold) but not the threshold itself. `mastered` is
 * rendered as a marker on top of the band color, never used to reassign a
 * band.
 */
const BANDS: Array<{ upperBound: number; key: PKnownBandKey; label: string }> = [
  { upperBound: 0.2, key: 'unseen', label: 'Unseen' },
  { upperBound: 0.4, key: 'emerging', label: 'Emerging' },
  { upperBound: 0.6, key: 'developing', label: 'Developing' },
  { upperBound: 0.85, key: 'approaching', label: 'Approaching' },
  { upperBound: Infinity, key: 'mastered', label: 'Mastered' },
]

export function pKnownBand(pKnown: number): PKnownBand {
  const band = BANDS.find((candidate) => pKnown < candidate.upperBound) ?? BANDS[BANDS.length - 1]
  return { key: band.key, label: band.label }
}
