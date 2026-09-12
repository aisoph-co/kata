/** Waits for the real API to be up and seeded before the suite runs a single
 * test against it — per decisions row 12, tests run against the real stack
 * `demo-up.sh` starts, not a mock. Ferry is the default seed (row 23); set
 * `E2E_SEED=golden` to run the suite against the synthetic fixture instead. */
async function globalSetup() {
  const apiTarget = process.env.API_TARGET ?? 'http://localhost:8000'
  const expectedSeed = process.env.E2E_SEED ?? 'ferry'
  const deadline = Date.now() + 60_000

  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${apiTarget}/health`)
      if (res.ok) {
        const body = (await res.json()) as { seed?: string }
        if (body.seed === expectedSeed) return
      }
    } catch {
      // API not up yet — keep polling.
    }
    await new Promise((r) => setTimeout(r, 1000))
  }

  throw new Error(
    `API at ${apiTarget}/health never reported seed: ${expectedSeed} within 60s. Run 'npm run demo' first.`,
  )
}

export default globalSetup
