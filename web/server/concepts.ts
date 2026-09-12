/**
 * Concept UUID -> human title, for the one thing the insight lane's text
 * answers need that `/me/progress`/`/me/history` don't return (they key
 * everything by UUID). Mirrors `web/src/lib/ferry-scenario.ts`'s `CONCEPTS`
 * table (the SPA's own label lookup for the same fixed Ferry-seed data) —
 * chart/card *rendering* stays entirely client-side and already imports
 * that file directly, so this copy exists only for phrasing this runtime's
 * own chat replies (e.g. naming the weakest concept).
 */

const TITLE_BY_ID: Record<string, string> = {
  '6dff3619-90fb-5e73-b3b5-f851f133a853': 'Challenge flow: mandated vs chosen',
  '500249ec-74cd-5fa0-8fdc-3829703581f0': 'Double-entry ledger',
  'e06c32bb-8ca5-510b-8301-1c4fffb2ed4c': 'FX quote lifecycle',
  '43a44a66-6645-5d39-ba3a-ca1a8dc0b0ce': 'Idempotency keys',
  'a1168744-2efc-5d6e-897e-bed08a708059': 'Ledger migrations',
  '659800b1-b6bc-5038-98ca-fe614f053f2b': 'Representing money',
  '83b47129-c886-5131-80fe-5e840bdc49ed': 'Payment state machine',
  '53935fdd-b2c6-5cd1-9cad-d97864474dac': 'Communicating an uncertain payment',
  '2e82572d-d515-5bc5-a87f-0831f10843ee': 'Payout and settlement',
  '3731907b-83d8-5360-b2d1-a67f6368ebcf': 'PSP contract testing',
  '3a2f5806-bd3e-55fe-9136-fe79ac465034': 'Reconciliation',
  '5bdafb6f-c0d4-5264-8370-def17d1a27ba': 'Retrying safely',
  'f08cb689-22bb-5732-87f8-93ee6fbc137a': 'SCA and exemptions',
  '22d2ffbb-898e-5035-9c00-2b4d4cf35266': 'Webhook delivery',
}

export function conceptTitle(id: string): string {
  return TITLE_BY_ID[id] ?? `concept ${id.slice(0, 8)}`
}
