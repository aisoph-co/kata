import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api-client'

interface ConceptGraphNode {
  concept_id: string
  slug: string
  title: string
}

interface ConceptGraphResponse {
  nodes: ConceptGraphNode[]
}

export interface ConceptTitle {
  slug: string
  title: string
}

type ConceptTitles = Record<string, ConceptTitle>

/**
 * `GET /me/concept-graph` carries every course concept's `title`/`slug`
 * (course-wide structure, not subtree-scoped) alongside the caller's own
 * `p_known` — the `/team/*` schemas only ever carry `concept_id`, so this
 * is how the heatmap and drill-down panel get a human-readable column
 * header instead of a raw UUID. The manager's own `p_known`/`mastered`/
 * `unlocked` fields on each node are unused here.
 */
export function useConceptTitles(header: string): ConceptTitles {
  const [titles, setTitles] = useState<ConceptTitles>({})

  useEffect(() => {
    let cancelled = false
    apiFetch<ConceptGraphResponse>('/me/concept-graph', { persona: { header } })
      .then((data) => {
        if (cancelled) return
        const byId: ConceptTitles = {}
        for (const node of data.nodes) byId[node.concept_id] = { slug: node.slug, title: node.title }
        setTitles(byId)
      })
      .catch(() => {
        // Titles are a display nicety; a failure here still leaves the
        // heatmap usable with concept ids as the fallback label.
      })
    return () => {
      cancelled = true
    }
  }, [header])

  return titles
}
