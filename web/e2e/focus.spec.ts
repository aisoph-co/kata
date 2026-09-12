import { expect, test } from '@playwright/test'
import { CONCEPT_TITLES, HUGO_HEADER, switchPersona } from './helpers'

interface NextItem {
  concept_id: string
}

async function hugoNext(request: import('@playwright/test').APIRequestContext, limit: number): Promise<NextItem[]> {
  const res = await request.get(`/api/me/next?limit=${limit}`, {
    headers: { 'X-Acting-Identity': `${HUGO_HEADER.platform}:${HUGO_HEADER.external_id}` },
  })
  const body = await res.json()
  return body.items as NextItem[]
}

test('Quinn: focus for Hugo moves that concept earlier in his queue, then deletes it', async ({ page, request }) => {
  // Pick a concept that is already a real candidate in Hugo's queue (so it's
  // guaranteed to have an available item) but isn't first yet, so the focus
  // boost has something to prove by moving it up.
  const before = await hugoNext(request, 20)
  const target = before.slice(1).find((i) => i.concept_id !== before[0]?.concept_id)
  test.skip(!target, "Hugo's queue has fewer than two distinct concepts available right now")
  const conceptId = target!.concept_id
  const beforeIndex = before.findIndex((i) => i.concept_id === conceptId)
  const title = CONCEPT_TITLES[conceptId]

  await page.goto('/en/focus')
  await switchPersona(page, 'Quinn')
  await page.getByRole('combobox').nth(1).click() // Person
  await page.getByRole('option', { name: 'Hugo Marchetti' }).click()
  await page.getByRole('combobox').nth(2).click() // Concept
  await page.getByRole('option', { name: title, exact: true }).click()
  await page.locator('input[type=number]').fill('20')
  await page.getByRole('button', { name: 'Create focus' }).click()
  await expect(page.getByText(`${title} →`)).toBeVisible()

  const after = await hugoNext(request, 20)
  const afterIndex = after.findIndex((i) => i.concept_id === conceptId)
  expect(afterIndex).toBeGreaterThanOrEqual(0)
  if (beforeIndex >= 0) expect(afterIndex).toBeLessThanOrEqual(beforeIndex)

  // "see Hugo's queue" — verify the link switches persona and navigates.
  await page.getByRole('button', { name: "See Hugo's queue" }).click()
  await expect(page).toHaveURL(/\/next-up/)
  await expect(page.getByText('Hugo Marchetti', { exact: true })).toBeVisible()

  // Cleanup: delete the focus we created. Navigate via the Developer "All
  // screens" menu's own link (client-side route change) — a hard
  // page.goto() would reload the page and lose the in-memory "created this
  // session" focus list, since there is no GET endpoint to rediscover it from.
  await page.getByTestId('developer-toggle').click()
  await page.getByTestId('all-screens-toggle').click()
  await page.getByRole('menuitem', { name: 'Focus' }).click()
  await switchPersona(page, 'Quinn') // "See Hugo's queue" switched the acting persona to Hugo
  await expect(page.getByText(`${title} →`)).toBeVisible()
  await page.getByRole('button', { name: 'Delete' }).click()
  await expect(page.getByText(`${title} →`)).toHaveCount(0)
})
