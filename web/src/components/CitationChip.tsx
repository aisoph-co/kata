import { classifyCitation, type CitationKind } from '@/lib/connections-model'

const TESTID_BY_KIND: Record<CitationKind, string> = {
  issue: 'cited-issue-id',
  thread: 'cited-thread',
  file: 'cited-file',
}

/**
 * One `Topic.grounded_in` entry, rendered as a click target. Clicking opens
 * the cited excerpt in place (`ExcerptPanel`, below the same card) — never a
 * new tab (SCREENS.md #02's done check).
 */
export function CitationChip({
  citation,
  isOpen,
  onToggle,
}: {
  citation: string
  isOpen: boolean
  onToggle: (citation: string) => void
}) {
  const kind = classifyCitation(citation)
  return (
    <button
      type="button"
      className="citation-chip"
      data-testid={TESTID_BY_KIND[kind]}
      aria-expanded={isOpen}
      aria-pressed={isOpen}
      onClick={() => onToggle(citation)}
    >
      {citation}
    </button>
  )
}
