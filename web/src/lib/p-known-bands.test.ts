import { describe, expect, it } from 'vitest'
import { pKnownBand } from './p-known-bands'

describe('pKnownBand', () => {
  it.each([
    [0, 'unseen'],
    [0.19, 'unseen'],
    [0.2, 'emerging'],
    [0.39, 'emerging'],
    [0.4, 'developing'],
    [0.59, 'developing'],
    [0.6, 'approaching'],
    [0.84, 'approaching'],
    [0.85, 'mastered'],
    [1, 'mastered'],
  ] as const)('bands %f as %s', (pKnown, key) => {
    expect(pKnownBand(pKnown).key).toBe(key)
  })
})
