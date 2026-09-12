import { expect, test } from '@playwright/test'

test('persona menu rows show role and channel', async ({ page }) => {
  await page.goto('/en/next-up')
  await page.getByTestId('persona-menu-trigger').click()

  await expect(page.getByTestId('persona-quinn').getByText('Tech lead · Slack')).toBeVisible()
  await expect(page.getByTestId('persona-daniel').getByText('Senior SWE · Slack')).toBeVisible()
  await expect(page.getByTestId('persona-hugo').getByText('Junior SWE · WhatsApp')).toBeVisible()
  await expect(page.getByTestId('persona-nushka').getByText('Junior SWE · Slack')).toBeVisible()
  await expect(page.getByTestId('persona-shane').getByText('PM · WhatsApp')).toBeVisible()

  // Unknown never resolves to a role — no role/channel line on its row.
  await expect(page.getByTestId('persona-unknown').getByTestId('persona-role-channel')).toHaveCount(0)

  // Secondary cast (Julian/Victor) is behind "More people".
  await expect(page.getByTestId('persona-julian')).toHaveCount(0)
  await page.getByTestId('persona-more-toggle').click()
  await expect(page.getByTestId('persona-julian').getByText('Junior SWE · Slack')).toBeVisible()
  await expect(page.getByTestId('persona-victor').getByText('Junior SWE · Slack')).toBeVisible()
})
