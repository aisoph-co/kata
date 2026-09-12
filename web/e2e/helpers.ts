import { expect, type APIRequestContext, type Page } from '@playwright/test'

export const PERSONS = {
  quinn: '1161cf71-d3df-51ce-85dd-7276f0c98dd4',
  daniel: '07a02952-92f9-5903-82b6-91a7a104e251',
  yongyi: '82f5bb91-d16b-596c-923b-726b9506b463',
  hugo: 'bd33e37f-cc6e-537a-99af-e01daae77bea',
  nushka: '6b32368e-138d-5db5-a9af-00190de556e2',
} as const

export const HUGO_HEADER = { platform: 'whatsapp', external_id: '447700900106' }

// Ferry-seed concept titles (agency-v1 learning_service/fixtures/ferry/
// concepts.json) — test-fixture knowledge, mirrors src/lib/ferry-scenario.ts.
export const CONCEPT_TITLES: Record<string, string> = {
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

// Ferry-seed concept slugs (mirrors src/lib/ferry-scenario.ts) — used to
// find a `mastery-row-<slug>` / heatmap column by concept_id.
export const CONCEPT_SLUGS: Record<string, string> = {
  '6dff3619-90fb-5e73-b3b5-f851f133a853': 'challenge-flow-ux',
  '500249ec-74cd-5fa0-8fdc-3829703581f0': 'double-entry',
  'e06c32bb-8ca5-510b-8301-1c4fffb2ed4c': 'fx-quote-lifecycle',
  '43a44a66-6645-5d39-ba3a-ca1a8dc0b0ce': 'idempotency',
  'a1168744-2efc-5d6e-897e-bed08a708059': 'ledger-migrations',
  '659800b1-b6bc-5038-98ca-fe614f053f2b': 'money-representation',
  '83b47129-c886-5131-80fe-5e840bdc49ed': 'payment-state-machine',
  '53935fdd-b2c6-5cd1-9cad-d97864474dac': 'payment-status-communication',
  '2e82572d-d515-5bc5-a87f-0831f10843ee': 'payout-settlement',
  '3731907b-83d8-5360-b2d1-a67f6368ebcf': 'psp-contract-testing',
  '3a2f5806-bd3e-55fe-9136-fe79ac465034': 'reconciliation',
  '5bdafb6f-c0d4-5264-8370-def17d1a27ba': 'retry-safety',
  'f08cb689-22bb-5732-87f8-93ee6fbc137a': 'sca-exemptions',
  '22d2ffbb-898e-5035-9c00-2b4d4cf35266': 'webhook-delivery',
}

const PERSONA_ID_BY_NAME = {
  Quinn: 'quinn',
  Daniel: 'daniel',
  Hugo: 'hugo',
  Nushka: 'nushka',
  Shane: 'shane',
  Unknown: 'unknown',
} as const

/** Opens the top-right persona avatar menu and clicks the named persona's
 * row (by data-testid — the visible label includes avatar initials, so
 * text matching is not exact-safe). Julian/Victor sit behind the "More
 * people" toggle, opened first if the row isn't already visible.
 *
 * A trigger click landing while the previous open's close animation is
 * still finishing can get swallowed by Radix — it looks "visible" for a
 * moment (mid exit-transition) but then finishes unmounting, taking the
 * target row with it before the click lands (seen consistently switching
 * personas twice in one test; more likely wherever the round trip to the
 * upstream API is a little slower, e.g. through the PLAN_10 Docker/Caddy
 * container vs the Vite proxy). Retrying just the trigger click once isn't
 * enough since the *row* — not the trigger — is what goes stale, so the
 * whole open-then-click sequence retries, bounding each row click short
 * (3s, not the test's full default) so a doomed attempt fails fast. */
export async function switchPersona(page: Page, name: keyof typeof PERSONA_ID_BY_NAME) {
  const trigger = page.getByTestId('persona-menu-trigger')
  const menu = page.getByRole('menu')
  const row = page.getByTestId(`persona-${PERSONA_ID_BY_NAME[name]}`)

  for (let attempt = 1; attempt <= 4; attempt++) {
    await trigger.click()
    const opened = await menu
      .waitFor({ state: 'visible', timeout: 2_000 })
      .then(() => true)
      .catch(() => false)
    if (!opened) continue

    const isPrimary = await row
      .waitFor({ state: 'visible', timeout: 800 })
      .then(() => true)
      .catch(() => false)
    if (!isPrimary) {
      const moreToggle = page.getByTestId('persona-more-toggle')
      if (await moreToggle.isVisible().catch(() => false)) await moreToggle.click()
    }

    const clicked = await row
      .click({ timeout: 3_000 })
      .then(() => true)
      .catch(() => false)
    if (clicked) return

    // The menu (or row) went stale mid-click — close out whatever's left
    // open and retry the whole sequence from a clean trigger click.
    await page.keyboard.press('Escape').catch(() => {})
  }
  throw new Error(`switchPersona(${name}): menu never stayed open long enough to click the row`)
}

// Mirrors src/lib/connect-store.ts's STORAGE_KEY.
const CONNECT_STORAGE_KEY = 'demo-web.connect'

/** Seeds localStorage with the given platform ids marked connected, before
 * any page script runs. KATA-15: connect-store no longer auto-seeds
 * Slack/WhatsApp into a fresh localStorage (a truly unseeded workspace must
 * land on zero connections), so specs that need a pre-connected state seed
 * it explicitly here instead of relying on the app's own default. Call
 * before the test's first `page.goto`.
 *
 * `addInitScript` re-runs on every navigation the test makes afterwards
 * (including a later `page.goto` back to a page mid-test), so the seed only
 * writes when localStorage is still untouched — otherwise it would stomp
 * connect/disconnect actions the test performs later in the same run. */
export async function seedConnections(page: Page, ids: string[]) {
  const value = JSON.stringify(Object.fromEntries(ids.map((id) => [id, true])))
  await page.addInitScript(
    ({ key, value }) => {
      if (window.localStorage.getItem(key) === null) window.localStorage.setItem(key, value)
    },
    { key: CONNECT_STORAGE_KEY, value },
  )
}

export type ItemKind = 'mcq' | 'msq' | 'self_rated' | 'short_answer' | 'teach_back' | null

/** The currently-shown Next up card, scoped by data-testid — never matched
 * by accessible-name substrings (an earlier version used `getByRole
 * ('button', {name: 'Again'})`, which also matched "Submit again (same
 * key)", misreading a just-graded mcq/msq/short_answer card as self_rated). */
function currentCard(page: Page) {
  return page.getByTestId('next-item-card')
}

/** Detects the kind of the item currently shown on Next up, from its own
 * answer-control testid — each kind renders exactly one, unconditionally,
 * graded or not. */
export async function currentItemKind(page: Page): Promise<ItemKind> {
  const card = currentCard(page)
  if (!(await card.isVisible().catch(() => false))) return null
  if (await card.getByTestId('mcq-options').isVisible().catch(() => false)) return 'mcq'
  if (await card.getByTestId('msq-options').isVisible().catch(() => false)) return 'msq'
  if (await card.getByTestId('self-rated-options').isVisible().catch(() => false)) return 'self_rated'
  if (await card.getByTestId('short-answer-text').isVisible().catch(() => false)) return 'short_answer'
  if (await card.getByText('teach_back items have no grader yet').isVisible().catch(() => false)) return 'teach_back'
  return null
}

/** Reads "Card X of Y" and returns Y — the actual size of the current
 * batch, since it can be smaller than the requested `limit` near the end
 * of the queue. Falls back to 5 (the default batch size) if unparseable. */
export async function currentBatchLength(page: Page): Promise<number> {
  const text = await page.getByTestId('batch-position').textContent().catch(() => null)
  const match = text?.match(/(\d+)$/)
  return match ? Number(match[1]) : 5
}

/** Submits a default response for whatever item is showing (mcq option A = always correct
 * in the Ferry fixture unless `wrong`, self_rated Good/Again, msq first option, short_answer filler text). */
export async function submitCurrent(page: Page, opts: { wrong?: boolean } = {}) {
  const card = currentCard(page)
  await card.waitFor({ state: 'visible' })
  const kind = await currentItemKind(page)
  if (kind === 'mcq') {
    const idx = opts.wrong ? 1 : 0
    const radio = card.getByRole('radio').nth(idx)
    await radio.click()
    await radio.waitFor({ state: 'visible' })
    await expect(radio).toBeChecked()
  } else if (kind === 'msq') {
    await card.getByRole('checkbox').first().click()
  } else if (kind === 'self_rated') {
    await card.getByTestId(opts.wrong ? 'rating-again' : 'rating-good').click()
  } else if (kind === 'short_answer') {
    await card.getByTestId('short-answer-text').fill('a filler answer for the demo suite')
  } else {
    return kind
  }
  await card.getByTestId('submit-answer').click()
  return kind
}

/** Clicks "Skip for now" on the current (ungraded) card — local only, moves
 * within the batch, no review written. Only valid before a submit; after
 * one, use advanceAfterSubmit instead (see its docstring for why). */
export async function skipCurrent(page: Page) {
  await currentCard(page).getByTestId('skip-for-now').click()
}

/**
 * Moves off a card *just submitted* by waiting for its own grading to
 * resolve (the "Next card" control replacing "Skip for now") and clicking
 * that — never races ahead and clicks "Skip for now" while the mutation is
 * still in flight. That race was the real cause of a rare "element
 * detached from DOM" flake: skipping (not advancing-via-next) the last
 * card in a batch wraps the local index instead of reloading, so the
 * still-pending submission's card could unmount and remount mid-click as a
 * real batch refetch landed moments later out of step with the test.
 */
export async function advanceAfterSubmit(page: Page, timeout = 10_000) {
  await currentCard(page).getByTestId('next-card').click({ timeout })
}

/** Sets Next up's batch-size control (5/10/20), which maps 1:1 to GET /me/next's `limit`. */
export async function setBatchSize(page: Page, size: 5 | 10 | 20) {
  const position = page.getByTestId('batch-position')
  const before = await position.textContent().catch(() => null)
  await page.getByTestId('batch-size-select').click()
  await page.getByRole('option', { name: String(size), exact: true }).click()
  // Wait for the new batch to actually land (position text changes — either
  // the count or which card is first) rather than a fixed timer.
  for (let i = 0; i < 50; i++) {
    const after = await position.textContent().catch(() => null)
    if (after && after !== before) return
    await page.waitForTimeout(100)
  }
}

// extra_items.json (agency-v1 fixtures/ferry): 2 msq + 2 teach_back + 1
// short_answer on top of the base 46-item bank = 5 extra items total.
export const EXTRA_ITEMS_TOTAL = 5
export const MAX_BATCH_LIMIT = 20

interface PersonaCandidate {
  name: 'Hugo' | 'Nushka'
  header: string
}

const EXTRA_ITEMS_CANDIDATES: PersonaCandidate[] = [
  { name: 'Hugo', header: 'whatsapp:447700900106' },
  { name: 'Nushka', header: 'slack:U0FERRY10' },
]

/**
 * Picks whichever of Hugo/Nushka's real max-size (20) `/me/next` batch
 * actually contains `kind` right now — checked against the live response,
 * not guessed from overdue counts (Ferry's real selection doesn't
 * re-offer an already-mastered concept's item as eagerly as golden's did,
 * so a headroom heuristic isn't reliable here). Returns null (with the
 * measurements) if neither's batch has it, so the caller can skip rather
 * than guess.
 */
export async function pickPersonaForKind(
  request: APIRequestContext,
  kind: ItemKind,
): Promise<{ persona: PersonaCandidate; measurements: string } | { persona: null; measurements: string }> {
  const measurements: string[] = []
  for (const candidate of EXTRA_ITEMS_CANDIDATES) {
    const res = await request.get(`/api/me/next?limit=${MAX_BATCH_LIMIT}`, {
      headers: { 'X-Acting-Identity': candidate.header },
    })
    const body = await res.json()
    const kinds = new Set(body.items.map((i: { kind: string }) => i.kind))
    measurements.push(`${candidate.name} kinds=${[...kinds].join('/')}`)
    if (kinds.has(kind)) {
      return { persona: candidate, measurements: measurements.join(', ') }
    }
  }
  return { persona: null, measurements: measurements.join(', ') }
}

/** Cycles the current (already-fetched) batch via Skip for now looking for
 * `kind` — no forced submission, since presence in this single batch is
 * already guaranteed by the caller (pickPersonaForFullBatch), and every
 * card stays ungraded throughout, so Skip for now is always the right
 * control (no advanceAfterSubmit race to worry about here). */
export async function findInCurrentBatch(page: Page, kind: ItemKind, maxAttempts = 25): Promise<boolean> {
  for (let i = 0; i < maxAttempts; i++) {
    await page.waitForTimeout(80)
    const current = await currentItemKind(page)
    if (current === kind) return true
    if (current === null) return false
    await skipCurrent(page)
  }
  return (await currentItemKind(page)) === kind
}

/**
 * Advances Next up looking for `kind`, within up to `maxBatches` fetched
 * batches. Cycles the current batch locally first via Skip for now (no API
 * call, every card still ungraded) — bounded by the batch's *actual* size
 * (read from "Card X of Y" / "Thẻ X/Y"), not a guess, so the cycle can't
 * wrap past the last card back into ones it has already looked at. If
 * `kind` isn't in the batch, overdue cards (mcq/self_rated from the
 * 60-day history) can occupy the whole batch ahead of any "new" candidate
 * — msq/short_answer/teach_back only ever appear as new items — so this
 * grades *every* gradeable card (never teach_back) to clear it in one
 * pass, waiting for each one's own grading via advanceAfterSubmit before
 * moving to the next.
 */
export async function advanceUntilKind(page: Page, kind: ItemKind, maxBatches = 6): Promise<boolean> {
  for (let batch = 0; batch < maxBatches; batch++) {
    const length = await currentBatchLength(page)
    for (let i = 0; i < length; i++) {
      await page.waitForTimeout(120)
      const current = await currentItemKind(page)
      if (current === kind) return true
      if (current === null) return false
      await skipCurrent(page)
    }
    // Full local cycle done, target not in this batch — clear it for real.
    // Answered *wrong* on purpose: this is just clearing overdue cards out
    // of the way, not testing correctness, and a correct answer moves
    // p_known enough that clearing the whole overdue backlog this way
    // masters most concepts before msq/short_answer/teach_back ever get a
    // chance to surface as new-item candidates.
    for (let i = 0; i < length; i++) {
      const current = await currentItemKind(page)
      if (current === null) break
      if (current === 'teach_back') {
        await skipCurrent(page)
      } else {
        await submitCurrent(page, { wrong: true })
        await advanceAfterSubmit(page)
      }
    }
    // Grading the last card in the loop above always clicks "Next card" at
    // the batch's final index, which reloads (see NextUp.tsx's onNext) —
    // wait for the fresh batch's first (ungraded) card before the next
    // outer pass reads state, or it would still see the just-graded last
    // card of the old batch and hang waiting for a "Skip for now" that
    // graded cards don't render.
    await currentCard(page)
      .getByTestId('skip-for-now')
      .waitFor({ state: 'visible', timeout: 10_000 })
      .catch(() => {})
  }
  return (await currentItemKind(page)) === kind
}
