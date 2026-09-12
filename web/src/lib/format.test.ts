import { describe, expect, it } from 'vitest'
import { formatPercent, formatRelativeDelta, formatSigned } from './format'

describe('formatPercent', () => {
  it('renders null as an em dash — a real value has not been computed', () => {
    expect(formatPercent(null)).toBe('—')
  })

  it('rounds to the nearest whole percent', () => {
    expect(formatPercent(0.865)).toBe('87%')
    expect(formatPercent(0)).toBe('0%')
  })
})

describe('formatSigned', () => {
  it('prefixes a plus for non-negative values', () => {
    expect(formatSigned(0.021)).toBe('+0.02')
  })

  it('prefixes a minus sign for negative values', () => {
    expect(formatSigned(-0.13)).toBe('−0.13')
  })

  it('renders null as an em dash', () => {
    expect(formatSigned(null)).toBe('—')
  })
})

describe('formatRelativeDelta', () => {
  const now = new Date('2026-09-12T12:00:00Z').getTime()

  it('is null when there is no last-active timestamp yet', () => {
    expect(formatRelativeDelta(null, now)).toBeNull()
  })

  it('reads "just now" for something under a minute old', () => {
    expect(formatRelativeDelta('2026-09-12T11:59:40Z', now)).toBe('just now')
  })

  it('reads in minutes, then hours, then days as the gap grows', () => {
    expect(formatRelativeDelta('2026-09-12T11:55:00Z', now)).toBe('5m ago')
    expect(formatRelativeDelta('2026-09-12T09:00:00Z', now)).toBe('3h ago')
    expect(formatRelativeDelta('2026-09-10T12:00:00Z', now)).toBe('2d ago')
  })
})
