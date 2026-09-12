import { useSyncExternalStore } from 'react'

/**
 * Connect is the one deliberate mock in this app (PLAN_08 decisions log):
 * 100% client-side, localStorage only, never calls the API. Everything
 * else in the demo reads real endpoints — this is the single exception,
 * and Team context's left panel + STREAM log are the only other surfaces
 * that read this state.
 */

export interface Platform {
  id: string
  name: string
  /** Brand accent colour for the tile/dialog chrome — the mark's own official hex. */
  color: string
  /** Fixed, plausible connected-state numbers (fake, deterministic per platform). */
  stats: { channels: number; membersMapped: number; threads: number }
  statLabelOverride?: { channels?: string; threads?: string }
}

// Five chat platforms only (2026-09-10 follow-up: Work/Search groups and
// Google Chat/Zalo dropped — one flat grid, no group header needed).
export const PLATFORMS: Platform[] = [
  { id: 'slack', name: 'Slack', color: '#4A154B', stats: { channels: 12, membersMapped: 9, threads: 5 } },
  { id: 'whatsapp', name: 'WhatsApp', color: '#25D366', stats: { channels: 4, membersMapped: 6, threads: 11 } },
  { id: 'teams', name: 'Teams', color: '#5059C9', stats: { channels: 8, membersMapped: 9, threads: 6 } },
  { id: 'discord', name: 'Discord', color: '#5865F2', stats: { channels: 6, membersMapped: 7, threads: 3 } },
  { id: 'telegram', name: 'Telegram', color: '#26A5E4', stats: { channels: 3, membersMapped: 5, threads: 4 } },
]

const STORAGE_KEY = 'demo-web.connect'

type ConnectState = Record<string, boolean>

// KATA-15: a truly fresh workspace starts at zero connections — nothing is
// auto-seeded into localStorage on first read. Team context's empty state
// (and every "Connect" row on /connect) depends on this being genuinely
// empty until a source is connected through the UI.
function readInitial(): ConnectState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as ConnectState
    return {}
  } catch {
    return {}
  }
}

let state: ConnectState = readInitial()
const listeners = new Set<() => void>()

function emit() {
  for (const l of listeners) l()
}

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // private browsing / storage disabled — state just won't survive reload
  }
}

export function setConnected(id: string, connected: boolean) {
  state = { ...state, [id]: connected }
  persist()
  emit()
}

export function isConnected(id: string): boolean {
  return !!state[id]
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot(): ConnectState {
  return state
}

/** Reactive connect-state map, keyed by platform id. */
export function useConnectState(): ConnectState {
  return useSyncExternalStore(subscribe, getSnapshot)
}

export function useConnectedPlatforms(): Platform[] {
  const connected = useConnectState()
  return PLATFORMS.filter((p) => connected[p.id])
}
