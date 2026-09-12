import { expect, test } from '@playwright/test'

test('Backstage is hidden by default; the Developer toggle brings it back', async ({ page }) => {
  await page.goto('/en/next-up')

  await expect(page.getByRole('button', { name: 'Backstage' })).toHaveCount(0)

  await page.getByTestId('developer-toggle').click()
  await expect(page.getByRole('button', { name: 'Backstage' })).toBeVisible()

  await page.getByTestId('developer-toggle').click()
  await expect(page.getByRole('button', { name: 'Backstage' })).toHaveCount(0)
})
