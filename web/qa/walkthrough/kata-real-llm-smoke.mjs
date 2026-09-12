// Throwaway QA script — Part 3 real-model smoke (agents/plans/PLAN_06 §Part 3).
// Answers one Hugo short_answer item correctly, and a different one with
// nonsense, against the real OpenRouter grader (LEARNING_LLM unset, see
// npm run demo:real-llm). Records grade/rating/explanation/latency.
import { chromium } from 'playwright-core'
import path from 'node:path'

const QA_DIR = path.resolve(import.meta.dirname, '..')
const BASE = 'http://localhost:5173'

function currentCard(page) {
  return page.getByTestId('next-item-card')
}
async function currentItemKind(page) {
  const card = currentCard(page)
  if (!(await card.isVisible().catch(() => false))) return null
  if (await card.getByTestId('mcq-options').isVisible().catch(() => false)) return 'mcq'
  if (await card.getByTestId('msq-options').isVisible().catch(() => false)) return 'msq'
  if (await card.getByTestId('self-rated-options').isVisible().catch(() => false)) return 'self_rated'
  if (await card.getByTestId('short-answer-text').isVisible().catch(() => false)) return 'short_answer'
  if (await card.getByText('teach_back items have no grader yet').isVisible().catch(() => false)) return 'teach_back'
  return null
}
async function skipCurrent(page) {
  const card = currentCard(page)
  const skipBtn = card.getByTestId('skip-for-now')
  if (await skipBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await skipBtn.click()
  }
}
async function setBatchSize(page, size) {
  const before = await page.getByTestId('batch-position').textContent().catch(() => null)
  await page.getByTestId('batch-size-select').click()
  await page.getByRole('option', { name: String(size), exact: true }).click()
  for (let i = 0; i < 50; i++) {
    const after = await page.getByTestId('batch-position').textContent().catch(() => null)
    if (after && after !== before) return
    await page.waitForTimeout(100)
  }
}

async function findItemId(page, itemId, maxTries = 20) {
  for (let i = 0; i < maxTries; i++) {
    const currentId = await currentCard(page).getAttribute('data-item-id').catch(() => null)
    if (currentId === itemId) return true
    const kind = await currentItemKind(page)
    if (kind === null) return false
    await skipCurrent(page)
    await page.waitForTimeout(100)
  }
  return false
}

async function answerAndMeasure(page, { itemId, text, label }) {
  const found = await findItemId(page, itemId)
  if (!found) {
    console.log(`[${label}] item ${itemId} not found in batch`)
    return null
  }
  const card = currentCard(page)
  const prompt = await card.locator('.text-base span').first().textContent().catch(() => '')
  await card.getByTestId('short-answer-text').fill(text)
  const started = Date.now()
  await card.getByTestId('submit-answer').click()
  await page.getByText('Graded').waitFor({ state: 'visible', timeout: 30_000 })
  const latencyMs = Date.now() - started
  const ratingText = await card.getByText(/^(Again|Hard|Good|Easy)$/).textContent().catch(() => '')
  const gradeText = await card
    .locator('span:text("Grade")')
    .locator('xpath=following-sibling::span[1]')
    .textContent()
    .catch(() => '')
  const explanation = await card.locator('.bg-muted.p-2').first().textContent().catch(() => '')
  await page.screenshot({ path: path.join(QA_DIR, `kata-qa-11-real-llm-${label}.png`) })
  return { prompt, text, ratingText, gradeText, explanation, latencyMs }
}

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  await page.goto(`${BASE}/en/next-up`)
  await page.getByTestId('persona-hugo').click()
  await page.waitForTimeout(500)
  await setBatchSize(page, 20)
  await page.waitForTimeout(500)

  const correct = await answerAndMeasure(page, {
    itemId: 'fe791c2b-7066-5e0e-91c8-ae43bdf0df60',
    label: 'correct',
    text:
      'It requires a real-time risk score computed by the acquirer/issuer at the moment of authorisation, before the transaction is approved, using signals available at that instant (device, behaviour, transaction context). It cannot be produced retrospectively because the exemption is meant to certify the fraud risk was assessed *before* the outcome was known — a score calculated after the fact could just be reverse-engineered from the known outcome, defeating the point of a real-time risk check that PSD2 RTS requires as part of the authorisation decision itself.',
  })
  console.log('CORRECT RESULT:', JSON.stringify(correct, null, 2))

  // Move to next card before hunting for the second target item.
  const nextBtn = currentCard(page).getByTestId('next-card')
  if (await nextBtn.isVisible({ timeout: 2000 }).catch(() => false)) await nextBtn.click()
  await page.waitForTimeout(300)

  const nonsense = await answerAndMeasure(page, {
    itemId: 'a3b30f0c-bd31-5490-9cfa-c3602c966162',
    label: 'nonsense',
    text: 'banana wizard clouds do the ordering because Tuesday is purple and the webhook eats gravity for breakfast',
  })
  console.log('NONSENSE RESULT:', JSON.stringify(nonsense, null, 2))

  await browser.close()
}

main().catch((err) => {
  console.error('FATAL', err)
  process.exit(1)
})
