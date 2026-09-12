import { useSyncExternalStore } from 'react'

/**
 * Minimal external store, no extra dependency. Good enough for the
 * persona selection and the Backstage call log.
 */
export function createStore<T>(initial: T) {
  let state = initial
  const listeners = new Set<() => void>()

  return {
    getState: () => state,
    setState: (updater: T | ((prev: T) => T)) => {
      state =
        typeof updater === 'function' ? (updater as (prev: T) => T)(state) : updater
      for (const listener of listeners) listener()
    },
    subscribe: (listener: () => void) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
  }
}

export function useStore<T>(store: ReturnType<typeof createStore<T>>): T {
  return useSyncExternalStore(store.subscribe, store.getState, store.getState)
}
