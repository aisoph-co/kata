/**
 * Human-readable labels for the fixed Ferry-seed dataset (decisions row 23:
 * it is the only fixture this demo runs against on `feat/demo-web`).
 * `/team/*` responses key everything by real roster UUIDs and never return
 * a name (confirmed by reading `agency-v1/learning_service/team/schemas.py`),
 * so this file — generated once from a live `LEARNING_SEED=ferry` API
 * (`/identities/resolve` per person, `/admin/concepts`) — is the label
 * lookup. It does not stand in for any API response: every number/state on
 * screen still comes from a real call: this only turns an id into a name.
 */

export interface FerryPerson {
  id: string
  name: string
  isOperator: boolean
}

export const PERSONS: FerryPerson[] = [
  { id: '5e648633-33d5-5789-914e-34ad675b96eb', name: 'Quinn Halloran', isOperator: true },
  { id: '07a02952-92f9-5903-82b6-91a7a104e251', name: 'Daniel Okonkwo', isOperator: false },
  { id: '55583884-32fd-5088-8be0-300de03f3e12', name: 'Yong Yi Tan', isOperator: false },
  { id: 'ed7b2f26-9925-54a2-a460-a70289595f56', name: 'Shane Delaney', isOperator: false },
  { id: 'b55b9c1f-bf5a-50fd-b00e-00b73d6823b1', name: 'Mei Lin Chua', isOperator: false },
  { id: 'b5c371a1-a791-534b-8035-f0121a33c677', name: 'Hugo Marchetti', isOperator: false },
  { id: '232575fc-3a43-52b1-ac22-3e7d831b4018', name: 'Julian Reyes', isOperator: false },
  { id: '2b82990e-8bac-56b2-8d83-f7e05033d10c', name: 'Victor Almeida', isOperator: false },
  { id: '3daa8b5e-96b0-5193-9451-52bb2a39fc87', name: 'Titus Nakamura', isOperator: false },
  { id: '6b32368e-138d-5db5-a9af-00190de556e2', name: 'Nushka Petrova', isOperator: false },
]

export interface FerryConcept {
  id: string
  slug: string
  title: string
}

export const CONCEPTS: FerryConcept[] = [
  { id: '6dff3619-90fb-5e73-b3b5-f851f133a853', slug: 'challenge-flow-ux', title: 'Challenge flow: mandated vs chosen' },
  { id: '500249ec-74cd-5fa0-8fdc-3829703581f0', slug: 'double-entry', title: 'Double-entry ledger' },
  { id: 'e06c32bb-8ca5-510b-8301-1c4fffb2ed4c', slug: 'fx-quote-lifecycle', title: 'FX quote lifecycle' },
  { id: '43a44a66-6645-5d39-ba3a-ca1a8dc0b0ce', slug: 'idempotency', title: 'Idempotency keys' },
  { id: 'a1168744-2efc-5d6e-897e-bed08a708059', slug: 'ledger-migrations', title: 'Ledger migrations' },
  { id: '659800b1-b6bc-5038-98ca-fe614f053f2b', slug: 'money-representation', title: 'Representing money' },
  { id: '83b47129-c886-5131-80fe-5e840bdc49ed', slug: 'payment-state-machine', title: 'Payment state machine' },
  { id: '53935fdd-b2c6-5cd1-9cad-d97864474dac', slug: 'payment-status-communication', title: 'Communicating an uncertain payment' },
  { id: '2e82572d-d515-5bc5-a87f-0831f10843ee', slug: 'payout-settlement', title: 'Payout and settlement' },
  { id: '3731907b-83d8-5360-b2d1-a67f6368ebcf', slug: 'psp-contract-testing', title: 'PSP contract testing' },
  { id: '3a2f5806-bd3e-55fe-9136-fe79ac465034', slug: 'reconciliation', title: 'Reconciliation' },
  { id: '5bdafb6f-c0d4-5264-8370-def17d1a27ba', slug: 'retry-safety', title: 'Retrying safely' },
  { id: 'f08cb689-22bb-5732-87f8-93ee6fbc137a', slug: 'sca-exemptions', title: 'SCA and exemptions' },
  { id: '22d2ffbb-898e-5035-9c00-2b4d4cf35266', slug: 'webhook-delivery', title: 'Webhook delivery' },
]

const PERSON_BY_ID = new Map(PERSONS.map((p) => [p.id, p]))
const CONCEPT_BY_ID = new Map(CONCEPTS.map((c) => [c.id, c]))

export function personName(id: string): string {
  return PERSON_BY_ID.get(id)?.name ?? `person ${id.slice(0, 8)}`
}

export function conceptTitle(id: string): string {
  return CONCEPT_BY_ID.get(id)?.title ?? `concept ${id.slice(0, 8)}`
}

export function conceptSlug(id: string): string {
  return CONCEPT_BY_ID.get(id)?.slug ?? id.slice(0, 8)
}
