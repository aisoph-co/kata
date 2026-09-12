import { createStore, useStore } from './store'

/**
 * Screen 2 (W1)'s confirmation state: has *this* signed-in person's role
 * been confirmed (or picked, via "Change") for the live session? Keyed by
 * person id so a re-resolve of a different person never inherits a stale
 * confirmation. `SessionGate` resets this the moment the session ends, so
 * nobody skips the confirm/change screen on a later sign-in.
 *
 * This never writes `person.role` back to the core — only a roster
 * re-import does that (contract change #8). It only decides which role
 * this session acts as.
 */
interface RoleConfirmState {
  personId: string | null
  role: string | null
}

const initialState: RoleConfirmState = { personId: null, role: null }

const roleConfirmStore = createStore<RoleConfirmState>(initialState)

export function useRoleConfirm(): RoleConfirmState {
  return useStore(roleConfirmStore)
}

export function confirmRole(personId: string, role: string) {
  roleConfirmStore.setState({ personId, role })
}

export function resetRoleConfirm() {
  roleConfirmStore.setState(initialState)
}
