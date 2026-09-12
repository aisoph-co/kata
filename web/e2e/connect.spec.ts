import { expect, test } from '@playwright/test'
import { seedConnections } from './helpers'

// Connect is 100% client-side (localStorage) — no API involved, so no
// switchPersona/backend setup is needed for these.

// KATA-15: a truly fresh workspace must start at zero connections (Team
// context's empty-state Done check) — nothing is auto-seeded anymore.
test('fresh browser: nothing is connected, every platform shows Connect', async ({ page }) => {
  await page.goto('/en/connect')
  for (const id of ['slack', 'whatsapp', 'teams', 'discord', 'telegram']) {
    await expect(page.getByTestId(`platform-tile-${id}`)).not.toContainText('Connected')
    await expect(page.getByTestId(`connect-${id}`)).toBeVisible()
  }
})

test('a previously connected platform stays connected on a later visit', async ({ page }) => {
  await seedConnections(page, ['slack', 'whatsapp'])
  await page.goto('/en/connect')
  await expect(page.getByTestId('platform-tile-slack')).toContainText('Connected')
  await expect(page.getByTestId('platform-tile-whatsapp')).toContainText('Connected')
  await expect(page.getByTestId('connect-teams')).toBeVisible()
})

test('connecting Teams runs the dialog + 4-step progress and lands on Connected; reload keeps it', async ({ page }) => {
  await page.goto('/en/connect')

  await page.getByTestId('connect-teams').click()
  await expect(page.getByTestId('connect-dialog')).toBeVisible()
  await page.getByTestId('connect-dialog-allow').click()

  await expect(page.getByTestId('connect-dialog-progress')).toBeVisible()
  await expect(page.getByTestId('connect-dialog-done')).toBeVisible({ timeout: 8_000 })
  await page.getByRole('button', { name: 'Done' }).click()

  await expect(page.getByTestId('platform-tile-teams')).toContainText('Connected')

  await page.reload()
  await expect(page.getByTestId('platform-tile-teams')).toContainText('Connected')

  // Disconnect reverts.
  await page.getByTestId('disconnect-teams').click()
  await expect(page.getByTestId('connect-teams')).toBeVisible()
})

test('exactly the five chat platforms are listed, one flat grid', async ({ page }) => {
  await page.goto('/en/connect')
  const ids = ['slack', 'whatsapp', 'teams', 'discord', 'telegram']
  for (const id of ids) {
    await expect(page.getByTestId(`platform-tile-${id}`)).toBeVisible()
  }
  // No group headers/cards left now that there's only one group.
  await expect(page.getByRole('heading', { name: 'Chat' })).toHaveCount(0)
  await expect(page.getByTestId('platform-tile-github')).toHaveCount(0)
  await expect(page.getByTestId('platform-tile-zalo')).toHaveCount(0)
})
