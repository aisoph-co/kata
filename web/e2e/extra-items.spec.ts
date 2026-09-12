import { expect, test } from '@playwright/test'
import { findInCurrentBatch, pickPersonaForKind, setBatchSize, skipCurrent, submitCurrent, switchPersona } from './helpers'

// extra_items.json (agency-v1 fixtures/ferry) additively seeds msq/
// teach_back/short_answer on concepts Hugo/Nushka already have unlocked.
// Both have a real overdue backlog, and Ferry's real selection doesn't
// re-offer an already-mastered concept's item as eagerly as golden's did
// (Hugo has mastered idempotency/money-representation, so msq on those
// concepts doesn't surface for him) — so each test picks whichever of
// Hugo/Nushka's real max-size (20) batch actually contains the kind it
// needs, checked against the live response. See helpers.ts pickPersonaForKind.

test.describe('Next up — extra item kinds, deterministic per-kind pick', () => {
  test('an msq card is present and grades', async ({ page, request }) => {
    const { persona, measurements } = await pickPersonaForKind(request, 'msq')
    test.skip(!persona, `Neither Hugo nor Nushka has an msq card in a 20-card batch (${measurements})`)

    await page.goto('/en/next-up')
    await switchPersona(page, persona!.name)
    await setBatchSize(page, 20)
    const found = await findInCurrentBatch(page, 'msq')
    expect(found, `${persona!.name}'s batch-20 response: ${measurements}`).toBe(true)
    await submitCurrent(page)
    await expect(page.getByText('Graded')).toBeVisible()
  })

  test('a short_answer card is present and grades', async ({ page, request }) => {
    const { persona, measurements } = await pickPersonaForKind(request, 'short_answer')
    test.skip(!persona, `Neither Hugo nor Nushka has a short_answer card in a 20-card batch (${measurements})`)

    await page.goto('/en/next-up')
    await switchPersona(page, persona!.name)
    await setBatchSize(page, 20)
    const found = await findInCurrentBatch(page, 'short_answer')
    expect(found).toBe(true)
    await submitCurrent(page)
    await expect(page.getByText('Graded')).toBeVisible()
  })

  test('a teach_back card is present and shows the no-grader notice', async ({ page, request }) => {
    const { persona, measurements } = await pickPersonaForKind(request, 'teach_back')
    test.skip(!persona, `Neither Hugo nor Nushka has a teach_back card in a 20-card batch (${measurements})`)

    await page.goto('/en/next-up')
    await switchPersona(page, persona!.name)
    await setBatchSize(page, 20)
    const found = await findInCurrentBatch(page, 'teach_back')
    expect(found).toBe(true)
    await expect(page.getByText('teach_back items have no grader yet')).toBeVisible()
  })

  test('Skip for now advances within a 20-card batch', async ({ page }) => {
    await page.goto('/en/next-up')
    await switchPersona(page, 'Hugo')
    await setBatchSize(page, 20)

    const before = await page.getByTestId('batch-position').textContent()
    await skipCurrent(page)
    const after = await page.getByTestId('batch-position').textContent()
    expect(after).not.toBe(before)
  })
})
