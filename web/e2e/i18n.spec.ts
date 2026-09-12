import { expect, test } from '@playwright/test'

// Locale coverage for the /vi route: loads in Vietnamese, checks a few key
// labels, then switches to English via the top-bar language control and
// confirms the same page (Progress) stays open, now in English.
test('vi loads Vietnamese; the language switch lands on the same page in English', async ({ page }) => {
  await page.goto('/vi/progress')

  await expect(page.locator('html')).toHaveAttribute('lang', 'vi')
  await expect(page.getByTestId('tab-progress')).toHaveText('Tiến độ')
  await expect(page.getByTestId('tab-team-context')).toHaveText('Team context')

  await page.getByTestId('lang-en').click()

  await expect(page).toHaveURL(/\/en\/progress$/)
  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await expect(page.getByTestId('tab-progress')).toHaveText('Progress')
})
