import i18n from '@/i18n'

/** API error codes with a translated one-line explanation available.
 * The raw code is always shown as-is next to whatever this returns —
 * never replaced by it. */
const KNOWN_CODES = [
  'unknown_identity',
  'not_a_manager',
  'not_operator',
  'outside_subtree',
  'note_cap',
  'no_grader',
  'network_error',
  'idempotency_replay',
  'unauthorized',
] as const

function toCamel(code: string): string {
  return code.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase())
}

/** Short, translated one-liner for a known API error code, or undefined
 * for anything not in the curated list (the raw code/message still show). */
export function errorExplanation(code: string | undefined): string | undefined {
  if (!code || !(KNOWN_CODES as readonly string[]).includes(code)) return undefined
  return i18n.t(`errors.${toCamel(code)}`)
}
