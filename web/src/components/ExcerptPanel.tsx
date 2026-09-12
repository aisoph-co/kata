import { resolveCitationExcerpt } from '@/lib/seed-citations'

/**
 * The cited artifact's excerpt, rendered in place under the citation chip
 * that opened it (SCREENS.md #02 done check: "renders in place, not a new
 * blank tab with nothing in it"). `resolveCitationExcerpt` reads the
 * vendored `1-context/` mirror — see its own doc comment for why this isn't
 * a core API call yet; a miss is shown as a stated gap, not left blank.
 */
export function ExcerptPanel({ citation }: { citation: string }) {
  const excerpt = resolveCitationExcerpt(citation)

  if (!excerpt) {
    return (
      <div className="excerpt-panel excerpt-panel--missing" data-testid="connections-excerpt-panel">
        <p className="excerpt-panel-missing">
          No excerpt on file for <code>{citation}</code> yet.
        </p>
      </div>
    )
  }

  return (
    <div className="excerpt-panel" data-testid="connections-excerpt-panel">
      <p className="excerpt-panel-source">
        {excerpt.sourceFile} — {excerpt.heading}
      </p>
      <p className="excerpt-panel-text">{excerpt.text}</p>
    </div>
  )
}
