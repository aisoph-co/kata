import { expect, test } from '@playwright/test'
import { switchPersona } from './helpers'

test.describe('Progress + notes — Hugo', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/en/progress')
    await switchPersona(page, 'Hugo')
  })

  test('Progress shows the four stat tiles and the mastery-per-concept table', async ({ page }) => {
    await expect(page.getByTestId('tile-retention')).toBeVisible()
    await expect(page.getByTestId('tile-mastery')).toBeVisible()
    await expect(page.getByTestId('tile-calibration')).toBeVisible()
    await expect(page.getByTestId('tile-bypass')).toBeVisible()
    await expect(page.getByTestId('mastery-per-concept')).toBeVisible()
  })

  test('add a note, delete it, and an over-cap note shows note_cap verbatim', async ({ page }) => {
    await page.goto('/en/answers-notes')
    await switchPersona(page, 'Hugo')

    const uniqueText = `e2e note ${Date.now()}`
    await page.getByPlaceholder('Add a note…').fill(uniqueText)
    await page.getByRole('button', { name: 'Add note' }).click()
    await expect(page.getByText(uniqueText)).toBeVisible()

    // Clean up: delete the note we just created (order-independence).
    const row = page.locator('li', { hasText: uniqueText })
    await row.getByRole('button').click()
    await expect(page.getByText(uniqueText)).toHaveCount(0)

    // Cap error, shown verbatim (500 chars/note — agency-v1 engine/models.py NOTE_MAX_CHARS).
    await page.getByPlaceholder('Add a note…').fill('x'.repeat(501))
    await page.getByRole('button', { name: 'Add note' }).click()
    await expect(page.getByText('at most 20 notes of 500 characters each')).toBeVisible()
  })
})
