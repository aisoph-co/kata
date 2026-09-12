import { expect, test } from '@playwright/test'
import { switchPersona } from './helpers'

test('persona switch re-resolves identity', async ({ page }) => {
  await page.goto('/en/next-up')
  await switchPersona(page, 'Hugo')
  await expect(page.getByText('Hugo Marchetti')).toBeVisible()
  await switchPersona(page, 'Quinn')
  await expect(page.getByText('Quinn Halloran')).toBeVisible()
})

test('Unknown persona shows 403 unknown_identity', async ({ page }) => {
  await page.goto('/en/next-up')
  await switchPersona(page, 'Unknown')
  // /me/* now also resolves the real person (agency-v1 PR #5), so both the
  // persona bar's resolve status and the Next up page itself show the 403 —
  // .first() just needs one of them visible.
  await expect(page.getByText('unknown_identity').first()).toBeVisible()
})
