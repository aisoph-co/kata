import { expect, test } from '@playwright/test'
import { switchPersona } from './helpers'

// Shane (whatsapp:447700900104), not Hugo: no other spec in this suite
// acts as Shane, so his state is untouched by whatever ran earlier —
// order-independent, unlike the file-order trick this replaced. Fresh
// Ferry seed gives Shane exactly 174 review rows (deterministic
// generator, see G-kata-seed.md §4); kept as a safety net in case a
// future spec does start touching him.
const SHANE_HEADER = 'whatsapp:447700900104'
const SHANE_SEED_REVIEW_COUNT = 174

interface ConceptProgress {
  concept_id: string
  p_known: number
}

async function shaneProgress(
  request: import('@playwright/test').APIRequestContext,
): Promise<{ concepts: ConceptProgress[]; reviewCount: number }> {
  const res = await request.get('/api/me/progress', { headers: { 'X-Acting-Identity': SHANE_HEADER } })
  const body = await res.json()
  return { concepts: body.concepts, reviewCount: body.summary.review_count }
}

test('Quinn: Replay reproduces Shane, including one freshly-submitted live review, identically', async ({
  request,
  page,
}) => {
  const preCheck = await shaneProgress(request)
  test.skip(
    preCheck.reviewCount > SHANE_SEED_REVIEW_COUNT,
    `Shane has ${preCheck.reviewCount} reviews (seed baseline ${SHANE_SEED_REVIEW_COUNT}) — live reviews present, run scripts/reset-demo-db.sh`,
  )

  // The mixed-history case PR #8 targets: seed's directly-written rows
  // plus one real, freshly-submitted review. Bypassed so it's valid for
  // whatever kind the next item happens to be (no per-kind response
  // needed) — the same real `POST /me/reviews` path the rep screen uses.
  const nextRes = await request.get('/api/me/next?limit=1', { headers: { 'X-Acting-Identity': SHANE_HEADER } })
  const next = await nextRes.json()
  const itemId = next.items[0]?.id
  expect(itemId, 'Shane has no next item to submit a live review for').toBeTruthy()
  const reviewRes = await request.post('/api/me/reviews', {
    headers: { 'X-Acting-Identity': SHANE_HEADER, 'Content-Type': 'application/json' },
    data: { item_id: itemId, idempotency_key: crypto.randomUUID(), bypassed: true, response: {} },
  })
  expect(reviewRes.ok(), `live review submit for Shane failed: ${reviewRes.status()} ${await reviewRes.text()}`).toBe(true)

  // Live-computed mixed-history state (seed rows + the one just above),
  // captured before replay recomputes anything from the log.
  const before = (await shaneProgress(request)).concepts

  // Drive the real UI action (the product feature), which is narrated
  // around Hugo's table — that assertion stays for regression coverage.
  await page.goto('/en/replay')
  await switchPersona(page, 'Quinn')
  await page.getByRole('button', { name: 'Run replay' }).click()
  await expect(page.getByText('reviews replayed')).toBeVisible({ timeout: 15_000 })

  const countBadge = await page.getByText('reviews replayed').textContent()
  const replayedCount = Number(countBadge?.match(/\d+/)?.[0] ?? 0)
  expect(replayedCount).toBeGreaterThan(50)

  const rows = page.locator('table tbody tr')
  const rowCount = await rows.count()
  expect(rowCount).toBeGreaterThan(0)
  for (let i = 0; i < rowCount; i++) {
    await expect(rows.nth(i)).toContainText('identical')
  }

  // The actual invariant this spec exists for: Shane's own mixed-history
  // p_known, read directly via the API (the Replay page only narrates
  // Hugo's), must be identical before vs. after the same replay run.
  const after = (await shaneProgress(request)).concepts
  for (const b of before) {
    const a = after.find((x) => x.concept_id === b.concept_id)
    expect(a, `Shane's ${b.concept_id} missing after replay`).toBeTruthy()
    expect(Math.abs((a?.p_known ?? NaN) - b.p_known), `Shane's ${b.concept_id} drifted on replay`).toBeLessThan(1e-9)
  }
})
