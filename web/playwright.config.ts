import { defineConfig, devices } from '@playwright/test'

// PLAN_10: point the suite at a running Docker/Caddy container instead of
// the Vite dev server by setting E2E_BASE_URL (e.g. http://localhost:8080).
// In that mode Playwright doesn't own any server (the container is already
// up), and auth-401.spec.ts is skipped — it's inherently a two-dev-server
// test (wrong SERVICE_TOKEN on a second Vite instance) with no equivalent
// against a container built with one fixed token.
const containerBaseURL = process.env.E2E_BASE_URL
const baseURL = containerBaseURL ?? 'http://localhost:5173'

export default defineConfig({
  testDir: './e2e',
  // Serialized on purpose: most tests act on the same real, shared Dee/Ada
  // state on the live API (no per-test DB reset), so parallel workers would
  // race each other's submissions and audit rows.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: 'list',
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  projects: containerBaseURL
    ? [{ name: 'chromium', use: { ...devices['Desktop Chrome'] }, testIgnore: /auth-401\.spec\.ts/ }]
    : [
        { name: 'chromium', use: { ...devices['Desktop Chrome'] }, testIgnore: /auth-401\.spec\.ts/ },
        {
          name: 'auth-401',
          use: { ...devices['Desktop Chrome'], baseURL: 'http://localhost:5174' },
          testMatch: /auth-401\.spec\.ts/,
        },
      ],
  // Two dev servers: the real app on 5173, and a second instance on 5174
  // started with an intentionally wrong SERVICE_TOKEN (.env.test401) so
  // auth-401.spec.ts can assert the real 401 without touching the main app's token.
  // Skipped entirely when E2E_BASE_URL targets an already-running container.
  webServer: containerBaseURL
    ? undefined
    : [
        { command: 'npm run dev', url: 'http://localhost:5173', reuseExistingServer: !process.env.CI, timeout: 30_000 },
        {
          command: 'npm run dev -- --port 5174 --mode test401',
          url: 'http://localhost:5174',
          reuseExistingServer: !process.env.CI,
          timeout: 30_000,
        },
      ],
})
