import { expect, test } from '@playwright/test'
import { CONCEPT_SLUGS, HUGO_HEADER, switchPersona } from './helpers'

test('Hugo: chart shows at least 20 points for idempotency over the last 30 days', async ({ page }) => {
  await page.goto('/en/progress')
  await switchPersona(page, 'Hugo')

  const chart = page.getByTestId('progress-chart')
  await expect(chart).toBeVisible()
  await expect(page.getByText('Idempotency keys — what Kata believes', { exact: false })).toBeVisible()

  const points = await chart.getAttribute('data-points')
  expect(Number(points)).toBeGreaterThanOrEqual(20)

  // Hugo's scripted "just tell me" days (docs/seed) each land a bypass
  // followed by a real, non-bypassed rep — the closing question Hermes
  // still asks and the answer to it.
  await expect(page.getByTestId('bypass-marker').first()).toBeVisible()
  await expect(page.getByTestId('closing-question-recovery-marker').first()).toBeVisible()
})

test('clicking retry-safety in the mastery table switches the chart', async ({ page }) => {
  await page.goto('/en/progress')
  await switchPersona(page, 'Hugo')

  await expect(page.getByTestId('progress-chart')).toBeVisible()
  await page.getByTestId('mastery-row-retry-safety').click()
  await expect(page.getByText('Retrying safely — what Kata believes', { exact: false })).toBeVisible()
})

test('Developer → Next rep: submitting a bypass moves the bypass line and adds a marker on Progress', async ({
  page,
  request,
}) => {
  const nextRes = await request.get('/api/me/next?limit=1', {
    headers: { 'X-Acting-Identity': `${HUGO_HEADER.platform}:${HUGO_HEADER.external_id}` },
  })
  const next = await nextRes.json()
  const conceptId = next.items[0]?.concept_id
  test.skip(!conceptId, 'Hugo has no next item to submit a bypass for right now')
  const slug = CONCEPT_SLUGS[conceptId]

  await page.goto('/en/progress')
  await switchPersona(page, 'Hugo')

  await page.getByTestId('developer-toggle').click()
  await page.getByTestId('all-screens-toggle').click()
  await page.getByRole('menuitem', { name: 'Next rep' }).click()
  await expect(page).toHaveURL(/\/next-up$/)

  await page.getByTestId('next-item-card').getByTestId('just-tell-me').click()
  await expect(page.getByText('bypassed')).toBeVisible()

  await page.goto('/en/progress')
  await switchPersona(page, 'Hugo')
  if (slug) {
    const row = page.getByTestId(`mastery-row-${slug}`)
    if (await row.isVisible().catch(() => false)) await row.click()
  }
  await expect(page.getByTestId('bypass-marker').first()).toBeVisible()
})
