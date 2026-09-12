import { createStore, useStore } from './store'

/**
 * The confirmed, resolved web session — set once Screen 1 (sign-in) and
 * Screen 2 (role confirmation) have both passed. `null` whenever there is
 * no live session: signed out, mid-gate, or Auth0 isn't configured for this
 * deployment. Screens built in later issues (W2-W4) read this instead of
 * re-resolving identity themselves, and reuse `header` as the
 * `X-Acting-Identity` value on every core call they make — the same
 * pattern Hermes uses for its own callers.
 */
export interface WebSession {
  personId: string
  displayName: string
  email: string
  isOperator: boolean
  role: string
  header: string
}

const webSessionStore = createStore<WebSession | null>(null)

export function setWebSession(session: WebSession) {
  webSessionStore.setState(session)
}

export function clearWebSession() {
  webSessionStore.setState(null)
}

export function useWebSession(): WebSession | null {
  return useStore(webSessionStore)
}
