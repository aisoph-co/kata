/**
 * The ferry cast's first names mapped to their roster UUIDs — the small
 * subset the chat router needs to recognise "how is <name> doing" turns.
 * Mirrors `web/src/lib/ferry-scenario.ts` (the full display-name label
 * lookup already shipped to the browser); not sensitive on its own, same
 * ids/names already ship client-side.
 */

export interface RosterPerson {
  firstName: string
  personId: string
}

export const ROSTER: RosterPerson[] = [
  { firstName: 'quinn', personId: '1161cf71-d3df-51ce-85dd-7276f0c98dd4' },
  { firstName: 'daniel', personId: '07a02952-92f9-5903-82b6-91a7a104e251' },
  { firstName: 'hugo', personId: 'bd33e37f-cc6e-537a-99af-e01daae77bea' },
  { firstName: 'nushka', personId: '6b32368e-138d-5db5-a9af-00190de556e2' },
  { firstName: 'shane', personId: '0b4b3ee0-5844-5672-80a9-047f3dcc1809' },
  { firstName: 'julian', personId: '232575fc-3a43-52b1-ac22-3e7d831b4018' },
  { firstName: 'victor', personId: '2b82990e-8bac-56b2-8d83-f7e05033d10c' },
  { firstName: 'yong yi', personId: '82f5bb91-d16b-596c-923b-726b9506b463' },
  { firstName: 'mei lin', personId: 'b55b9c1f-bf5a-50fd-b00e-00b73d6823b1' },
  { firstName: 'titus', personId: '3daa8b5e-96b0-5193-9451-52bb2a39fc87' },
]

/** First (case-insensitive, whole-word) roster name mentioned in `text`, or
 * `null`. Used only to route "how is X doing" turns to the manager-scoped
 * `/team/people/{id}` call — the backend's own `require_manager`/subtree
 * check decides whether the asker is actually allowed to see that person. */
export function findPersonByName(text: string): RosterPerson | null {
  for (const person of ROSTER) {
    const pattern = new RegExp(`\\b${person.firstName.replace(' ', '\\s+')}\\b`, 'i')
    if (pattern.test(text)) return person
  }
  return null
}
