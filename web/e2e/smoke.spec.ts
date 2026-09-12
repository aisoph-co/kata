import { expect, test } from '@playwright/test'

test('app loads on Team context with the four-tab teal header, no sidebar', async ({ page }) => {
  await page.goto('/en')

  await expect(page).toHaveURL(/\/en\/team-context$/)
  await expect(page.getByText('KATA', { exact: true })).toBeVisible()

  // Four tabs (Team hidden for the default persona, Hugo, a non-manager).
  await expect(page.getByTestId('tab-team-context')).toBeVisible()
  await expect(page.getByTestId('tab-progress')).toBeVisible()
  await expect(page.getByTestId('tab-connect')).toBeVisible()
  await expect(page.getByTestId('tab-team')).toHaveCount(0)

  // No sidebar nav.
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
  await expect(page.locator('aside')).toHaveCount(0)

  // Persona avatar menu, top-right.
  await expect(page.getByTestId('persona-menu-trigger')).toBeVisible()
})
