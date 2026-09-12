/**
 * The five ingestion sources team-context is grounded in (PRD §3 stage 1 /
 * KATA-11): repo, issues, releases, Slack, Exa. Counts are derived from the
 * `LEARNING_SEED=ferry` fixtures actually loaded (`docs/seed/1-context/`),
 * not a live crawl. `issues` is CI1's real, live source (KATA-22): triggering
 * ingestion below streams real `concept` rows out of `GET /admin/ingest`
 * against `docs/seed/1-context/issues.jsonl`, replacing this static count —
 * `repo`/`releases`/`slack`/`exa` stay static mirrors of the seed content
 * (same pattern as connect-store.ts's fixed platform stats) until CI2
 * extends real extraction to them.
 */

export interface IngestionSource {
  id: 'repo' | 'issues' | 'releases' | 'slack' | 'exa'
  label: string
  count: string
}

export const INGESTION_SOURCES: IngestionSource[] = [
  { id: 'repo', label: 'ferry monorepo', count: '8 excerpts' },
  { id: 'issues', label: 'PAY-1826 … PAY-1880', count: '26 issues' },
  { id: 'releases', label: 'orchestrator · ledger · webhook-gateway', count: '8 releases · 4 weeks' },
  { id: 'slack', label: '#payments-team · #payments-incidents', count: '5 threads' },
  { id: 'exa', label: 'PSD2 SCA exemptions, 1 Oct change', count: '1 result' },
]

/** A concept as streamed by `GET /admin/ingest` (`ingestion.py`'s `event:
 * concept` frames). */
export interface IngestedConcept {
  id: string
  slug: string
  title: string
  description: string
}

export type IngestionStreamEvent =
  | { type: 'concept'; concept: IngestedConcept }
  | { type: 'empty' }
  | { type: 'done'; course_id: string; concept_count: number }
  | { type: 'error'; message: string }

/**
 * Consumes `GET /admin/ingest`'s Server-Sent Event stream, calling
 * `onEvent` once per frame as it arrives. Hand-rolled rather than
 * `EventSource`: the route needs the service-token bearer (proxy-injected,
 * see api-client.ts) and `X-Acting-Identity` headers, neither of which
 * `EventSource` can send.
 */
export async function streamIngestion(
  persona: { header: string },
  onEvent: (event: IngestionStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  try {
    const response = await fetch('/api/admin/ingest', {
      headers: { 'X-Acting-Identity': persona.header },
      signal,
    })
    if (!response.ok || !response.body) {
      onEvent({ type: 'error', message: `ingest request failed (${response.status})` })
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let boundary: number
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const type = frame.match(/^event: (.+)$/m)?.[1] ?? 'message'
        const dataLine = frame.match(/^data: (.+)$/m)?.[1] ?? '{}'
        onEvent({ type, ...JSON.parse(dataLine) } as IngestionStreamEvent)
      }
    }
  } catch (cause) {
    // A caller-initiated abort (persona switch, unmount) is expected
    // teardown, not a failure worth surfacing to `onEvent`.
    if (cause instanceof DOMException && cause.name === 'AbortError') return
    onEvent({ type: 'error', message: cause instanceof Error ? cause.message : 'network error' })
  }
}
