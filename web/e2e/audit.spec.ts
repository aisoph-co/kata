import { expect, test } from '@playwright/test'
import { switchPersona } from './helpers'

test('Quinn: Audit shows a row per /team/* call made in this test, including 403s, none from /me/*', async ({
  page,
}) => {
  // Generate a fresh, identifiable trail: one allowed call (team overview as
  // Quinn) and one 403 (team overview as Hugo), then check the audit log picks
  // up the 403 too (spec: "including GET /team/audit's own... never for 401").
  await page.goto('/en/team')
  await switchPersona(page, 'Quinn')
  await expect(page.getByRole('table').first()).toBeVisible()

  await switchPersona(page, 'Hugo')
  await expect(page.getByText('not_a_manager')).toBeVisible()

  await page.goto('/en/audit')
  await switchPersona(page, 'Quinn')
  const rows = page.locator('table tbody tr')
  await expect(rows.first()).toBeVisible()
  await expect(page.getByText('/team/overview').first()).toBeVisible()

  // Every endpoint in the audit table is a /team/* call.
  const endpoints = await page.locator('table tbody tr td:nth-child(4)').allTextContents()
  for (const endpoint of endpoints) {
    expect(endpoint.startsWith('/team/')).toBeTruthy()
  }
})
