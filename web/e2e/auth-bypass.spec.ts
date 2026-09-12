import { expect, test } from '@playwright/test'

// AGCTM-64 finding #5: the e2e auth bypass. `build-day/tests/e2e` in the
// hackathon repo drives the three web screens through a real Auth0 gate
// (W1) with no tenant it can log into, so the web app honours a bypass —
// only when E2E_AUTH_BYPASS_TOKEN is set on the service *and* the request
// carries the same value. This spec pins both halves: the 404 half runs on
// every suite run (Vite dev server and the Caddy container alike), the
// 200 half only where the test env knows the token.
const TOKEN = process.env.E2E_AUTH_BYPASS_TOKEN
const EMAIL = process.env.E2E_LEARNER_EMAIL ?? 'hugo.marchetti@ferry.example'
const BYPASS_HEADERS = { 'X-E2E-Auth-Bypass': TOKEN ?? '', 'X-E2E-Learner-Email': EMAIL }

test('/__e2e/session is a 404 without the bypass header, and with a wrong token', async ({ request }) => {
  const bare = await request.get('/__e2e/session')
  expect(bare.status()).toBe(404)

  const wrong = await request.get('/__e2e/session', {
    headers: { 'X-E2E-Auth-Bypass': 'not-the-token', 'X-E2E-Learner-Email': EMAIL },
  })
  expect(wrong.status()).toBe(404)
})

test.describe('with E2E_AUTH_BYPASS_TOKEN set on both sides', () => {
  test.skip(!TOKEN, 'E2E_AUTH_BYPASS_TOKEN not set in the test env')

  test('/__e2e/session echoes the learner email for the right token', async ({ request }) => {
    const res = await request.get('/__e2e/session', { headers: BYPASS_HEADERS })
    expect(res.status()).toBe(200)
    expect(await res.json()).toEqual({ email: EMAIL })
  })

  test('a browser carrying the bypass headers lands past sign-in, acting as the learner', async ({ browser }) => {
    const context = await browser.newContext({ extraHTTPHeaders: BYPASS_HEADERS })
    const page = await context.newPage()
    await page.goto('/en/progress')

    // Neither Screen 1's sign-in card nor Screen 2's confirm gate — the
    // app shell itself, as the resolved seed learner.
    await expect(page.getByTestId('persona-menu-trigger')).toBeVisible()
    await expect(page.getByTestId('sign-in-button')).toHaveCount(0)
    await expect(page.getByTestId('role-confirm')).toHaveCount(0)
    await expect(page.getByTestId('sign-in-refused')).toHaveCount(0)
    await context.close()
  })
})
