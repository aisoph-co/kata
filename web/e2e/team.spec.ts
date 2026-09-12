import { expect, test } from '@playwright/test'
import { PERSONS, switchPersona } from './helpers'

test('Quinn: heatmap has 9 people and 14 concepts', async ({ page }) => {
  await page.goto('/en/team')
  await switchPersona(page, 'Quinn')
  const table = page.getByTestId('team-heatmap')
  await expect(table).toBeVisible()
  // One row per person + the team-mean row.
  const rows = table.locator('tbody tr')
  await expect(rows).toHaveCount(10)
  await expect(page.getByTestId('team-mean-row')).toBeVisible()
  // Person + 14 concepts + Adherence.
  const headerCells = table.locator('thead th')
  await expect(headerCells).toHaveCount(16)
})

test('Daniel sees only his subtree (3 reports: Hugo, Julian, Victor)', async ({ page }) => {
  await page.goto('/en/team')
  await switchPersona(page, 'Daniel')
  const table = page.getByTestId('team-heatmap')
  const rows = table.locator('tbody tr')
  await expect(rows).toHaveCount(4) // 3 reports + team-mean row
  await expect(page.getByText('outside_subtree')).toHaveCount(0)
})

test('Hugo gets not_a_manager', async ({ page }) => {
  await page.goto('/en/team')
  await switchPersona(page, 'Hugo')
  await expect(page.getByText('not_a_manager')).toBeVisible()
})

test('Daniel opening Nushka gets outside_subtree', async ({ page }) => {
  await page.goto(`/en/team/${PERSONS.nushka}`)
  await switchPersona(page, 'Daniel')
  await expect(page.getByText('outside_subtree')).toBeVisible()
})

test('Shane gets not_a_manager on a direct link (Team tab hidden for non-managers)', async ({ page }) => {
  await page.goto('/en/team')
  await switchPersona(page, 'Shane')
  await expect(page.getByTestId('tab-team')).toHaveCount(0)
  await expect(page.getByText('not_a_manager')).toBeVisible()
})
