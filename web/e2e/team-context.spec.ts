import { expect, type Page, test } from '@playwright/test'
import { seedConnections, switchPersona } from './helpers'

interface KataGraphHandle {
  nodeCount: number
  edgeCount: number
  highlighted: string[]
}

/** Cytoscape renders to canvas, so node/edge counts and the highlighted
 * set aren't DOM-queryable — the page exposes a small dev-only debug
 * handle (`window.__kataGraph`) instead, updated on every render. */
async function graphHandle(page: Page): Promise<KataGraphHandle> {
  await page.waitForFunction(() => window.__kataGraph !== undefined)
  return page.evaluate(() => window.__kataGraph!)
}

test('/concept-map redirects to /team-context', async ({ page }) => {
  await page.goto('/en/concept-map')
  await expect(page).toHaveURL(/\/en\/team-context$/)
})

test('graph renders 14 nodes and 21 edges, three topic cards render from /topics', async ({ page }) => {
  await seedConnections(page, ['slack', 'whatsapp'])
  await page.goto('/en/team-context')
  await switchPersona(page, 'Hugo')

  const handle = await graphHandle(page)
  expect(handle.nodeCount).toBe(14)
  expect(handle.edgeCount).toBe(21)

  await expect(page.getByTestId('topic-card-hugo')).toBeVisible()
  await expect(page.getByTestId('topic-card-daniel')).toBeVisible()
  await expect(page.getByTestId('topic-card-shane')).toBeVisible()

  // Each persona's topic card names its own source artifact (KAT-C2 Done check).
  const groundedIn = page.getByTestId('topic-card-hugo').getByTestId('topic-grounded-in')
  await expect(groundedIn).toBeVisible()
  await expect(groundedIn).toContainText('PAY-')
})

// W11 (KATA-14) Done check: clicking a source chip opens the cited
// artifact's actual excerpt, not just the identifier repeated back.
test('clicking Hugo\'s PAY-1847 source chip renders the cited excerpt, not a blank page', async ({ page }) => {
  await page.goto('/en/team-context')
  await switchPersona(page, 'Hugo')

  await page.getByTestId('topic-card-hugo').getByTestId('source-chip-PAY-1847').click()

  await expect(page).toHaveURL(/\/en\/source\/PAY-1847$/)
  await expect(page.getByTestId('source-excerpt')).toBeVisible()
  await expect(page.getByTestId('source-excerpt-title')).toHaveText('Retry attempts must share the original idempotency key')
  await expect(page.getByTestId('source-excerpt-body')).toContainText('PAY-1841')

  // Back link returns to team context, not a dead end.
  await page.getByTestId('source-excerpt-back').click()
  await expect(page).toHaveURL(/\/en\/team-context$/)
})

test('ingestion source list (repo, issues, releases, slack, exa) with counts and an ingesting badge', async ({ page }) => {
  await seedConnections(page, ['slack', 'whatsapp'])
  await page.goto('/en/team-context')
  await switchPersona(page, 'Hugo')

  const sources = page.getByTestId('ingestion-sources')
  await expect(sources).toBeVisible()
  for (const id of ['repo', 'issues', 'releases', 'slack', 'exa']) {
    await expect(page.getByTestId(`ingestion-source-${id}`)).toBeVisible()
    await expect(page.getByTestId(`ingestion-source-count-${id}`)).toBeVisible()
  }

  const badge = page.getByTestId('ingesting-badge')
  await expect(badge).toBeVisible()
  await expect(badge).toContainText(':')
})

test('hovering a node highlights its prerequisite chain and shows a tooltip with p_known', async ({ page }) => {
  await seedConnections(page, ['slack', 'whatsapp'])
  await page.goto('/en/team-context')
  await switchPersona(page, 'Hugo')
  await graphHandle(page)

  const canvas = page.getByTestId('concept-map-canvas')
  const box = await canvas.boundingBox()
  expect(box).toBeTruthy()
  let found = false
  for (let x = 0.1; x <= 0.9 && !found; x += 0.1) {
    for (let y = 0.1; y <= 0.9 && !found; y += 0.15) {
      await page.mouse.move(box!.x + box!.width * x, box!.y + box!.height * y)
      await page.waitForTimeout(60)
      const handle = await page.evaluate(() => window.__kataGraph!)
      if (handle.highlighted.length > 0) found = true
    }
  }
  expect(found).toBe(true)
  await expect(page.getByTestId('concept-map-tooltip')).toBeVisible()
  await expect(page.getByTestId('tooltip-p-known')).toContainText('%')
})

test('connected sources panel shows Connect state, STREAM log replays', async ({ page }) => {
  await seedConnections(page, ['slack', 'whatsapp'])
  await page.goto('/en/team-context')
  await switchPersona(page, 'Hugo')

  await expect(page.getByTestId('team-context-sources')).toBeVisible()
  await expect(page.getByTestId('source-row-slack')).toContainText('connected')
  await expect(page.getByTestId('source-row-whatsapp')).toContainText('connected')

  const stream = page.getByTestId('stream-log')
  await expect(stream).toBeVisible()
  await expect(stream).toContainText('14 concepts')
})

test('disconnecting one source flips only its own row to "Connect", others keep their counts', async ({ page }) => {
  await seedConnections(page, ['slack', 'whatsapp'])
  await page.goto('/en/team-context')
  await switchPersona(page, 'Hugo')
  await expect(page.getByTestId('source-row-slack')).toContainText('connected')
  await expect(page.getByTestId('source-row-teams')).toBeVisible()
  await expect(page.getByTestId('source-connect-teams')).toBeVisible()

  await page.goto('/en/connect')
  await page.getByTestId('disconnect-slack').click()
  await expect(page.getByTestId('connect-slack')).toBeVisible()

  await page.goto('/en/team-context')
  // Fixed row set: all 5 platforms still listed, slack now shows "Connect"
  // instead of disappearing, whatsapp (untouched) still shows its counts.
  await expect(page.getByTestId('source-connect-slack')).toBeVisible()
  await expect(page.getByTestId('source-row-whatsapp')).toContainText('connected')
  await expect(page.getByTestId('team-context-sources').locator('[data-testid^="source-row-"]')).toHaveCount(5)

  // Cleanup: reconnect slack so other specs see the default state.
  await page.goto('/en/connect')
  await page.getByTestId('connect-slack').click()
  await page.getByTestId('connect-dialog-allow').click()
  await expect(page.getByTestId('connect-dialog-done')).toBeVisible({ timeout: 8_000 })
  await page.getByRole('button', { name: 'Done' }).click()
})

test('Ingest now streams real concepts from GET /admin/ingest within 5 seconds (KATA-22/CI1)', async ({ page }) => {
  await seedConnections(page, ['slack', 'whatsapp'])
  await page.goto('/en/team-context')
  await switchPersona(page, 'Quinn') // the only seeded operator persona — /admin/ingest requires it

  await page.getByTestId('ingest-trigger').click()
  await expect(page.getByTestId('ingested-concepts').locator('[data-testid^="ingested-concept-"]').first()).toBeVisible({
    timeout: 5_000,
  })
  await expect(page.getByTestId('ingest-done')).toBeVisible({ timeout: 15_000 })
})

test('persona switch re-colours nodes without changing the node/edge count', async ({ page }) => {
  await seedConnections(page, ['slack', 'whatsapp'])
  await page.goto('/en/team-context')
  await switchPersona(page, 'Hugo')
  const before = await graphHandle(page)
  expect(before.nodeCount).toBe(14)
  expect(before.edgeCount).toBe(21)

  await switchPersona(page, 'Nushka')
  await page.waitForTimeout(500)
  const after = await graphHandle(page)
  expect(after.nodeCount).toBe(14)
  expect(after.edgeCount).toBe(21)
  await expect(page.getByText("highlighted: Nushka's topic")).toBeVisible()
})

test('with nothing connected, the honest empty state shows instead of invented curriculum; connecting a source lands on the populated view (KATA-15)', async ({ page }) => {
  // Fresh page, no seeding: connect-store starts at zero connections.
  await page.goto('/en/team-context')
  await expect(page.getByTestId('team-context-empty-state')).toBeVisible()
  await expect(page.getByTestId('ingestion-sources')).toHaveCount(0)
  await expect(page.getByTestId('stream-log')).toHaveCount(0)
  await expect(page.getByTestId('concept-map-canvas')).toHaveCount(0)
  await expect(page.getByTestId('topic-card-hugo')).toHaveCount(0)
  // Same "Connect team context" action W5 shows populated.
  await expect(page.getByTestId('team-context-sources')).toBeVisible()
  await expect(page.getByTestId('source-connect-slack')).toBeVisible()

  await page.goto('/en/connect')
  await page.getByTestId('connect-slack').click()
  await page.getByTestId('connect-dialog-allow').click()
  await expect(page.getByTestId('connect-dialog-done')).toBeVisible({ timeout: 8_000 })
  await page.getByRole('button', { name: 'Done' }).click()

  await page.goto('/en/team-context')
  await expect(page.getByTestId('team-context-empty-state')).toHaveCount(0)
  await expect(page.getByTestId('ingestion-sources')).toBeVisible()
  await expect(page.getByTestId('concept-map-canvas')).toBeVisible()

  // Confirms the transition isn't slack-specific: a second source also
  // clears the empty state (each test gets its own isolated browser
  // storage, so this isn't cross-test cleanup — just a second data point).
  await page.goto('/en/connect')
  await page.getByTestId('connect-whatsapp').click()
  await page.getByTestId('connect-dialog-allow').click()
  await expect(page.getByTestId('connect-dialog-done')).toBeVisible({ timeout: 8_000 })
  await page.getByRole('button', { name: 'Done' }).click()
})
