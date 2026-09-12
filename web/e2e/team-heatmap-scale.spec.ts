import { expect, test } from '@playwright/test'
import { switchPersona } from './helpers'

const BAND_CLASSES = ['bg-kata-heat-1', 'bg-kata-heat-2', 'bg-kata-heat-3', 'bg-kata-heat-4', 'bg-kata-heat-5']

test.describe('Team heatmap — 5-band scale (PLAN_08)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/en/team')
    await switchPersona(page, 'Quinn')
    await expect(page.getByTestId('team-heatmap')).toBeVisible()
  })

  test('every cell renders 0.00–1.00 with two decimals', async ({ page }) => {
    const cells = page.getByTestId('heatmap-cell')
    const count = await cells.count()
    expect(count).toBeGreaterThan(0)
    const texts = await cells.allTextContents()
    for (const text of texts) {
      expect(text).toMatch(/^\d\.\d{2}$/)
      const value = Number(text)
      expect(value).toBeGreaterThanOrEqual(0)
      expect(value).toBeLessThanOrEqual(1)
    }
  })

  test('cell colour matches its 5-band value', async ({ page }) => {
    const cells = page.getByTestId('heatmap-cell')
    const count = await cells.count()
    for (let i = 0; i < count; i++) {
      const cell = cells.nth(i)
      const value = Number(await cell.textContent())
      const className = (await cell.getAttribute('class')) ?? ''
      const expected =
        value < 0.25 ? BAND_CLASSES[0] : value < 0.5 ? BAND_CLASSES[1] : value < 0.7 ? BAND_CLASSES[2] : value < 0.85 ? BAND_CLASSES[3] : BAND_CLASSES[4]
      expect(className).toContain(expected)
    }
  })

  test('legend shows all five bands', async ({ page }) => {
    const legend = page.getByTestId('heatmap-legend')
    await expect(legend).toContainText('< 0.25')
    await expect(legend).toContainText('0.25–0.5')
    await expect(legend).toContainText('0.5–0.7')
    await expect(legend).toContainText('0.7–0.85')
    await expect(legend).toContainText('0.85')
  })

  test('adherence column and team-mean row are present', async ({ page }) => {
    await expect(page.getByRole('columnheader', { name: 'Adherence' })).toBeVisible()
    const meanRow = page.getByTestId('team-mean-row')
    await expect(meanRow).toBeVisible()
    await expect(meanRow).toContainText('team mean')
  })

  test('"What the manager gets" names the lowest-mean concept and lowest-adherence person', async ({ page }) => {
    const card = page.getByTestId('manager-gets-card')
    await expect(card).toBeVisible()
    await expect(page.getByTestId('manager-gets-team-gap')).toBeVisible()
    await expect(page.getByTestId('manager-gets-adherence')).toBeVisible()
    await expect(page.getByTestId('manager-gets-top-gap')).toBeVisible()
    await expect(card).toContainText('Never shown here')
    await expect(page.getByTestId('manager-gets-audit')).toContainText('/team/overview')
  })
})
