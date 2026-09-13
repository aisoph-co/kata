export type Role = 'learner' | 'manager' | 'operator'

export interface Persona {
  id: string
  name: string
  /** X-Acting-Identity header value */
  header: string
  roles: Role[]
  /** Ferry-cast role label (tech_lead/senior_swe/junior_swe/pm), shown on the persona chip. */
  role: string
  /** Human channel label for the header's platform, shown on the persona chip. */
  channel: string
  /** Real roster UUID (Ferry seed) — undefined for Unknown, which resolves to no person. */
  personId?: string
  /** Secondary cast — tucked behind the persona menu's "More people" toggle
   * instead of always-visible, so the primary five stay uncluttered. */
  secondary?: boolean
  /** Avatar background colour (persona menu) — categorical, not API data. */
  avatarColor: string
}

// Blurbs live in the locale files (personaBar.blurb.<id>), keyed by `id`
// below — they're UI copy, not API data, so they get translated there.
export const PERSONAS: Persona[] = [
  {
    id: 'quinn',
    name: 'Quinn',
    header: 'slack:U0C03BWUVEE',
    roles: ['manager', 'operator'],
    role: 'tech_lead',
    channel: 'Slack',
    personId: '5e648633-33d5-5789-914e-34ad675b96eb',
    avatarColor: '#4c3f91',
  },
  {
    id: 'daniel',
    name: 'Daniel',
    header: 'slack:U0FERRY02',
    roles: ['manager'],
    role: 'senior_swe',
    channel: 'Slack',
    personId: '07a02952-92f9-5903-82b6-91a7a104e251',
    avatarColor: '#8a3b2b',
  },
  {
    id: 'hugo',
    name: 'Hugo',
    header: 'whatsapp:447700900106',
    roles: ['learner'],
    role: 'junior_swe',
    channel: 'WhatsApp',
    personId: 'b5c371a1-a791-534b-8035-f0121a33c677',
    avatarColor: '#0f6b5b',
  },
  {
    id: 'nushka',
    name: 'Nushka',
    header: 'slack:U0FERRY10',
    roles: ['learner'],
    role: 'junior_swe',
    channel: 'Slack',
    personId: '6b32368e-138d-5db5-a9af-00190de556e2',
    avatarColor: '#7a5c1e',
  },
  {
    id: 'shane',
    name: 'Shane',
    header: 'whatsapp:447700900104',
    roles: ['learner'],
    role: 'pm',
    channel: 'WhatsApp',
    personId: 'ed7b2f26-9925-54a2-a460-a70289595f56',
    avatarColor: '#8a2f2f',
  },
  {
    id: 'julian',
    name: 'Julian',
    header: 'slack:U0FERRY07',
    roles: ['learner'],
    role: 'junior_swe',
    channel: 'Slack',
    personId: '232575fc-3a43-52b1-ac22-3e7d831b4018',
    secondary: true,
    avatarColor: '#2b5a8a',
  },
  {
    id: 'victor',
    name: 'Victor',
    header: 'slack:U0FERRY08',
    roles: ['learner'],
    role: 'junior_swe',
    channel: 'Slack',
    personId: '2b82990e-8bac-56b2-8d83-f7e05033d10c',
    secondary: true,
    avatarColor: '#3f7a4b',
  },
  {
    id: 'unknown',
    name: 'Unknown',
    header: 'slack:U0NOBODY',
    roles: [],
    role: 'unknown',
    channel: 'Slack',
    avatarColor: '#6b6b6b',
  },
]

export const DEFAULT_PERSONA_ID = 'hugo'

export function getPersona(id: string): Persona {
  return PERSONAS.find((p) => p.id === id) ?? PERSONAS[0]
}

/** Splits an `X-Acting-Identity` header value into the resolve-request shape. */
export function parseHeader(header: string): { platform: string; external_id: string } {
  const [platform, external_id] = header.split(':')
  return { platform, external_id }
}
