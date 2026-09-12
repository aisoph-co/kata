import { expect, test } from '@playwright/test'

// These two assertions need Hugo's state close to how `npm run demo` (or
// scripts/reset-demo-db.sh) seeded it — before his overdue backlog has
// been consumed by other tests or by clicking around the demo. Rather than
// relying on this file sorting first (a positional contract that silently
// breaks under --grep, sharding, or a rename), each test checks the real
// precondition itself and skips with a clear reason if it doesn't hold.

test.describe('Fresh Hugo state', () => {
  test.beforeEach(async ({ request }) => {
    const dueRes = await request.get('/api/me/due-summary', {
      headers: { 'X-Acting-Identity': 'whatsapp:447700900106' },
    })
    const due = await dueRes.json()
    test.skip(due.overdue_count === 0, 'Hugo already consumed — run scripts/reset-demo-db.sh')
  })

  test("Hugo's Progress shows his 60-day history before answering anything", async ({ request, page }) => {
    // /me/* resolves to the real Person.id, so Hugo's seeded review history
    // (Ferry seed: 261 reviews over 60 days) is visible without submitting
    // a single review — p_known should already be off the 0.2 P_INIT
    // baseline for at least one concept.
    const res = await request.get('/api/me/progress', { headers: { 'X-Acting-Identity': 'whatsapp:447700900106' } })
    const body = await res.json()
    const nonDefault = body.concepts.filter((c: { p_known: number }) => Math.abs(c.p_known - 0.2) > 0.02)
    expect(nonDefault.length).toBeGreaterThan(0)

    // Same story in the UI.
    await page.goto('/en/progress')
    await page.getByTestId('persona-menu-trigger').click()
    await page.getByTestId('persona-hugo').click()
    const list = page.getByTestId('mastery-per-concept')
    await expect(list).toBeVisible()
    const texts = await list.locator('span.tabular-nums').allTextContents()
    const anyAboveBaseline = texts.some((t) => {
      const value = Number(t.trim())
      return Number.isFinite(value) && value > 0.22
    })
    expect(anyAboveBaseline).toBe(true)
  })

  test("Hugo's Next up shows an overdue card first", async ({ request }) => {
    // Selection order is overdue (by retrievability) before new items
    // (agency-v1 engine/selection.py) — with real history now visible via
    // /me/*, Hugo should have overdue cards, and the first item back from
    // GET /me/next should be one of them (due_count > 0 for its concept).
    const nextRes = await request.get('/api/me/next?limit=1', {
      headers: { 'X-Acting-Identity': 'whatsapp:447700900106' },
    })
    const next = await nextRes.json()
    const firstConceptId = next.items[0]?.concept_id
    expect(firstConceptId).toBeTruthy()

    const progressRes = await request.get('/api/me/progress', {
      headers: { 'X-Acting-Identity': 'whatsapp:447700900106' },
    })
    const progress = await progressRes.json()
    const concept = progress.concepts.find((c: { concept_id: string }) => c.concept_id === firstConceptId)
    expect(concept?.due_count).toBeGreaterThan(0)
  })
})
