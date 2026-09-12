import { createStore, useStore } from './store'

export interface BackstageCall {
  id: string
  timestamp: number
  method: string
  path: string
  headers: Record<string, string>
  body: unknown
  status: number
  response: unknown
  durationMs: number
  /** True for a client-only event (e.g. "Skip for now") that never hit the network. */
  local?: boolean
}

const MAX_CALLS = 50

const backstageStore = createStore<BackstageCall[]>([])

export function recordBackstageCall(call: Omit<BackstageCall, 'id' | 'timestamp'>) {
  backstageStore.setState((prev) => {
    const entry: BackstageCall = {
      ...call,
      id: crypto.randomUUID(),
      timestamp: Date.now(),
    }
    return [entry, ...prev].slice(0, MAX_CALLS)
  })
}

/** Records a local-only action (no request left the browser) so Backstage
 * stays honest about what did and didn't happen — e.g. skipping a card. */
export function recordLocalEvent(entry: { label: string; note: string; detail?: unknown }) {
  recordBackstageCall({
    method: 'LOCAL',
    path: entry.label,
    headers: {},
    body: entry.detail ?? null,
    status: 0,
    response: { note: entry.note },
    durationMs: 0,
    local: true,
  })
}

export function clearBackstage() {
  backstageStore.setState([])
}

export function useBackstageCalls(): BackstageCall[] {
  return useStore(backstageStore)
}
