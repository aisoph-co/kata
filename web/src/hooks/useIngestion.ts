import { useCallback, useRef, useState } from 'react'

/**
 * `POST /admin/ingest` (KATA-13/CI1) — the "Connect team context" trigger
 * behind `Connections.tsx`'s `connections-connect-action` button. The route
 * streams one newline-delimited JSON object per row it writes (`type`:
 * `concept` | `edge` | `topic` | `item` | `empty` | `done`); this hook reads
 * that stream directly rather than polling `useConnectionsData`'s snapshot
 * endpoints, so a concept is counted the instant its own event arrives
 * (SCREENS.md #02: "first concept visible within 5 seconds") — `onSettled`
 * is the hook's one call back into that snapshot, to pull the authoritative
 * graph/topics once a run finishes.
 *
 * Bypasses `apiFetch` (`lib/api-client.ts`) on purpose: that helper always
 * buffers the full response body via `.text()`, which would defeat
 * streaming here — this is the one caller in the app that reads
 * `response.body` incrementally instead.
 */

export type IngestionStatus = 'idle' | 'running' | 'empty' | 'done' | 'error'

export interface IngestionState {
  status: IngestionStatus
  conceptCount: number
  topicCount: number
  error: string | null
}

interface IngestionEvent {
  type: 'concept' | 'edge' | 'topic' | 'item' | 'empty' | 'done'
  [key: string]: unknown
}

const IDLE: IngestionState = { status: 'idle', conceptCount: 0, topicCount: 0, error: null }

export function useIngestion(header: string, onSettled: () => void) {
  const [state, setState] = useState<IngestionState>(IDLE)
  const onSettledRef = useRef(onSettled)
  onSettledRef.current = onSettled

  const start = useCallback(async () => {
    setState({ status: 'running', conceptCount: 0, topicCount: 0, error: null })

    let response: Response
    try {
      response = await fetch('/api/admin/ingest', {
        method: 'POST',
        headers: { 'X-Acting-Identity': header },
      })
    } catch {
      setState({ status: 'error', conceptCount: 0, topicCount: 0, error: 'API not reachable' })
      return
    }

    if (!response.ok || !response.body) {
      setState({ status: 'error', conceptCount: 0, topicCount: 0, error: `ingestion failed: ${response.status}` })
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.trim()) continue
          applyEvent(JSON.parse(line) as IngestionEvent, setState)
        }
      }
      if (buffer.trim()) applyEvent(JSON.parse(buffer) as IngestionEvent, setState)
    } catch (cause) {
      setState((s) => ({ ...s, status: 'error', error: (cause as Error).message }))
      return
    }

    onSettledRef.current()
  }, [header])

  return { ...state, start }
}

function applyEvent(event: IngestionEvent, setState: (updater: (s: IngestionState) => IngestionState) => void) {
  switch (event.type) {
    case 'concept':
      setState((s) => ({ ...s, conceptCount: s.conceptCount + 1 }))
      return
    case 'topic':
      setState((s) => ({ ...s, topicCount: s.topicCount + 1 }))
      return
    case 'empty':
      setState((s) => ({ ...s, status: 'empty' }))
      return
    case 'done':
      setState((s) => ({ ...s, status: 'done' }))
      return
    default:
      return
  }
}
