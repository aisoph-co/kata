import { useSyncExternalStore } from 'react'

/**
 * The smallest possible client router: no cached path — `useRoute` always
 * reads `window.location.pathname` itself (`useSyncExternalStore`'s
 * snapshot), and `navigate`/`popstate` only need to signal "something
 * changed, re-read it". No router dependency: W2 only needs two paths
 * (`/reps`, `/dashboard`) and the Caddy/`vite.config.ts` SPA fallback
 * (`web/README.md`) already serves `index.html` for both, including a
 * direct load at either one.
 */
const listeners = new Set<() => void>()

function currentPath(): string {
  return typeof window === 'undefined' ? '/' : window.location.pathname
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  window.addEventListener('popstate', listener)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('popstate', listener)
  }
}

export function navigate(path: string) {
  if (currentPath() === path) return
  window.history.pushState({}, '', path)
  for (const listener of listeners) listener()
}

export function useRoute(): string {
  return useSyncExternalStore(subscribe, currentPath, () => '/')
}
