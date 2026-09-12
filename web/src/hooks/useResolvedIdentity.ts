import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { usePersona } from '@/lib/persona-store'
import { parseHeader, type Persona } from '@/lib/personas'

export interface PersonSummary {
  id: string
  display_name: string
  email: string
  is_operator: boolean
}

/** Resolves the given persona (defaults to the active one) via POST /identities/resolve. */
export function useResolvedIdentity(persona?: Persona) {
  const active = usePersona()
  const target = persona ?? active
  return useQuery({
    queryKey: ['identity-resolve', target.id],
    queryFn: () =>
      apiFetch<PersonSummary>('/identities/resolve', {
        persona: target,
        method: 'POST',
        body: parseHeader(target.header),
      }),
    retry: false,
  })
}
