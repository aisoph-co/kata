import { expect, test } from '@playwright/test'
import { PERSONS, switchPersona } from './helpers'

// KATA-13/W10: the row click-through on top of W6's heatmap (frame 11) —
// opens a side panel in place, no navigation away from the heatmap.
test('Quinn: clicking Hugo\'s row opens a concept-level side panel, heatmap stays put', async ({ page }) => {
  await page.goto('/en/team')
  await switchPersona(page, 'Quinn')
  await expect(page.getByTestId('team-heatmap')).toBeVisible()

  await page.getByTestId(`team-person-${PERSONS.hugo}`).click()

  const panel = page.getByTestId('person-drill-panel')
  await expect(panel).toBeVisible()
  // Concept-level fields only — no item/answer/transcript field anywhere.
  await expect(panel.getByRole('table')).toBeVisible()
  await expect(panel.getByTestId('person-panel-audit')).toBeVisible()
  // Still on /en/team, not navigated to a standalone drilldown route.
  await expect(page).toHaveURL(/\/en\/team$/)
  await expect(page.getByTestId('team-heatmap')).toBeVisible()
})

test('Quinn: the panel audit line reflects this specific read, not the overview load', async ({ page }) => {
  await page.goto('/en/team')
  await switchPersona(page, 'Quinn')
  await page.getByTestId(`team-person-${PERSONS.hugo}`).click()

  const panelAudit = await page.getByTestId('person-panel-audit').textContent()
  expect(panelAudit).toContain(`/team/people/${PERSONS.hugo}`)
})
