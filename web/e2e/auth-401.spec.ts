import { expect, test } from '@playwright/test'
import { switchPersona } from './helpers'

// Runs against the second dev server (port 5174, .env.test401) which the
// Vite proxy configures with an intentionally wrong SERVICE_TOKEN — the
// real service must answer 401, not a client-side guess.
test('wrong service token shows 401', async ({ page }) => {
  await page.goto('/en/next-up')
  await switchPersona(page, 'Hugo')
  await expect(page.getByText('unauthorized').first()).toBeVisible()
})
