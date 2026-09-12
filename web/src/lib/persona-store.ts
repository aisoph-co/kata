import { DEFAULT_PERSONA_ID, getPersona, type Persona } from './personas'
import { createStore, useStore } from './store'

const STORAGE_KEY = 'demo-web.persona'

function readInitial(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_PERSONA_ID
  } catch {
    return DEFAULT_PERSONA_ID
  }
}

const personaIdStore = createStore<string>(readInitial())

export function setPersonaId(id: string) {
  personaIdStore.setState(id)
  try {
    localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // private browsing / storage disabled — persona just won't survive reload
  }
}

export function getPersonaId(): string {
  return personaIdStore.getState()
}

/** Current persona, reactive. The sign-in gate (AE-24) is a doorman only —
 * it never swaps this out, so the demo picker's stored id is always the
 * acting persona, signed in or not. */
export function usePersona(): Persona {
  const id = useStore(personaIdStore)
  return getPersona(id)
}
