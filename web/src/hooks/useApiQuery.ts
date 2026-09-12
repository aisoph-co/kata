import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { usePersona } from '@/lib/persona-store'

/**
 * Thin wrapper around TanStack Query for the shared apiFetch client.
 * Keyed by the acting persona so switching personas refetches automatically.
 */
export function useApiQuery<T>(key: string, path: string, options: { enabled?: boolean } = {}) {
  const persona = usePersona()
  return useQuery({
    queryKey: [key, persona.id],
    queryFn: () => apiFetch<T>(path, { persona }),
    enabled: options.enabled ?? true,
    retry: false,
    staleTime: 10_000,
  })
}
