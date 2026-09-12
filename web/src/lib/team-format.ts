import type { ConceptTitle } from '@/hooks/useConceptTitles'

/** `TeamPersonSummary`/`TeamConceptDetailResponse` carry `person_id` only —
 * no `display_name` (the contract has no manager-facing roster-with-names
 * read). Until a contract row adds one, every person label in this screen
 * falls back to a short, stable slice of the id rather than inventing a
 * name. */
export function personLabel(personId: string): string {
  return `Person ${personId.slice(0, 8)}`
}

export function conceptLabel(conceptId: string, titles: Record<string, ConceptTitle>): string {
  return titles[conceptId]?.title ?? `Concept ${conceptId.slice(0, 8)}`
}

export function formatPercent(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`
}

export function formatTimestamp(iso: string | null): string {
  if (!iso) return '—'
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString()
}
