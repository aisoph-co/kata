import { createStore, useStore } from './store'

export interface FocusOut {
  id: string
  scope_kind: string
  scope_person_id: string
  concept_id: string
  set_by: string
  weight: number
  expires_at: string | null
  created_at: string
}

// There is no GET list endpoint for focus rows (agency-v1 team/router.py
// only has POST/DELETE) — this remembers what this browser session created,
// so it survives navigating away (e.g. "see Hugo's queue") and back. It is
// not a substitute for a real list: a reload starts empty again.
const focusStore = createStore<FocusOut[]>([])

export function addCreatedFocus(focus: FocusOut) {
  focusStore.setState((prev) => [focus, ...prev.filter((f) => f.id !== focus.id)])
}

export function removeCreatedFocus(id: string) {
  focusStore.setState((prev) => prev.filter((f) => f.id !== id))
}

export function useCreatedFocuses(): FocusOut[] {
  return useStore(focusStore)
}
