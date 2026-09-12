/** Shared display formatting for W2's two screens. */

export function formatPercent(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`
}

export function formatSigned(value: number | null, digits = 2): string {
  if (value === null) return '—'
  const sign = value >= 0 ? '+' : '−'
  return `${sign}${Math.abs(value).toFixed(digits)}`
}

/**
 * Relative-time delta for a tile's "last changed" badge (frame 09: bypass
 * tile reads "just now" right after a rep). General-purpose — not seeded
 * data specific — so it reads correctly whenever `last_active` actually is
 * recent, live demo included.
 */
export function formatRelativeDelta(iso: string | null, now: number = Date.now()): string | null {
  if (!iso) return null
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return null
  const seconds = Math.max(0, Math.round((now - then) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}
