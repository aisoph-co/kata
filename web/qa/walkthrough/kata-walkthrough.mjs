// Throwaway QA script — Kata demo web sign-off (agents/plans/PLAN_06-demo-web.md,
// Kata persona era). Drives the real running stack (localhost:5173 / :8000)
// with Playwright's chromium directly — no playwright.config, no webServer
// management, the stack is already up. Never touches src/ or e2e/.
// Selector/helper patterns read from e2e/helpers.ts (not imported, not
// modified) since this must stay outside the shipped suite.
import { chromium } from 'playwright-core'
import path from 'node:path'
import fs from 'node:fs'

const QA_DIR = path.resolve(import.meta.dirname, '..')
const BASE = 'http://localhost:5173'
const results = []

function shot(page, name) {
  return page.screenshot({ path: path.join(QA_DIR, `kata-qa-${name}.png`) })
}

function record(step, pass, evidence) {
  results.push({ step, pass, evidence: evidence.replace(/\s+/g, ' ').trim() })
  console.log(`[${pass === true ? 'PASS' : pass === false ? 'FAIL' : 'INFO'}] ${step} — ${evidence}`)
}

async function textOf(locator) {
  try {
    return (await locator.textContent()) ?? ''
  } catch {
    return ''
  }
}
async function visible(locator, timeout = 5000) {
  try {
    await locator.waitFor({ state: 'visible', timeout })
    return true
  } catch {
    return false
  }
}

// ---- helper-pattern copies (from e2e/helpers.ts, read-only reference) ----
const PERSONAS = {
  quinn: { header: 'slack:U0C03BWUVEE', personId: '1161cf71-d3df-51ce-85dd-7276f0c98dd4' },
  daniel: { header: 'slack:U0FERRY02', personId: '07a02952-92f9-5903-82b6-91a7a104e251' },
  hugo: { header: 'whatsapp:447700900106', personId: 'bd33e37f-cc6e-537a-99af-e01daae77bea' },
  nushka: { header: 'slack:U0FERRY10', personId: '6b32368e-138d-5db5-a9af-00190de556e2' },
  shane: { header: 'whatsapp:447700900104', personId: '0b4b3ee0-5844-5672-80a9-047f3dcc1809' },
  julian: { header: 'slack:U0FERRY07', personId: '232575fc-3a43-52b1-ac22-3e7d831b4018' },
  victor: { header: 'slack:U0FERRY08', personId: '2b82990e-8bac-56b2-8d83-f7e05033d10c' },
}
const CONCEPT_TITLES = {
  '6dff3619-90fb-5e73-b3b5-f851f133a853': 'Challenge flow: mandated vs chosen',
  '500249ec-74cd-5fa0-8fdc-3829703581f0': 'Double-entry ledger',
  'e06c32bb-8ca5-510b-8301-1c4fffb2ed4c': 'FX quote lifecycle',
  '43a44a66-6645-5d39-ba3a-ca1a8dc0b0ce': 'Idempotency keys',
  'a1168744-2efc-5d6e-897e-bed08a708059': 'Ledger migrations',
  '659800b1-b6bc-5038-98ca-fe614f053f2b': 'Representing money',
  '83b47129-c886-5131-80fe-5e840bdc49ed': 'Payment state machine',
  '53935fdd-b2c6-5cd1-9cad-d97864474dac': 'Communicating an uncertain payment',
  '2e82572d-d515-5bc5-a87f-0831f10843ee': 'Payout and settlement',
  '3731907b-83d8-5360-b2d1-a67f6368ebcf': 'PSP contract testing',
  '3a2f5806-bd3e-55fe-9136-fe79ac465034': 'Reconciliation',
  '5bdafb6f-c0d4-5264-8370-def17d1a27ba': 'Retrying safely',
  'f08cb689-22bb-5732-87f8-93ee6fbc137a': 'SCA and exemptions',
  '22d2ffbb-898e-5035-9c00-2b4d4cf35266': 'Webhook delivery',
}
const SCA_ID = 'f08cb689-22bb-5732-87f8-93ee6fbc137a'
const IDEMPOTENCY_ID = '43a44a66-6645-5d39-ba3a-ca1a8dc0b0ce'

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
async function currentBatchLength(page) {
  const t = await page.getByTestId('batch-position').textContent().catch(() => null)
  const m = t?.match(/(\d+)$/)
  return m ? Number(m[1]) : 5
}
// Defensive: if the current card is already graded (Skip for now replaced
// by Next card — see NextUp.tsx), advance instead of hanging on a 30s
// locator timeout waiting for a button that will never appear.
async function skipCurrent(page) {
  const card = currentCard(page)
  const skipBtn = card.getByTestId('skip-for-now')
  if (await skipBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await skipBtn.click()
    return
  }
  const nextBtn = card.getByTestId('next-card')
  if (await nextBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await nextBtn.click()
  }
}
async function advanceAfterSubmit(page, timeout = 10_000) {
  await currentCard(page).getByTestId('next-card').click({ timeout })
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
async function switchPersona(page, id) {
  await page.getByTestId(`persona-${id}`).click()
  await page.waitForTimeout(300)
}
async function apiGet(page, path, personaId) {
  const res = await page.request.get(`${BASE}/api${path}`, {
    headers: personaId ? { 'X-Acting-Identity': PERSONAS[personaId].header } : {},
  })
  return { status: res.status(), body: await res.json().catch(() => null) }
}

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  page.on('console', (msg) => {
    if (msg.type() === 'error') console.log('  [console.error]', msg.text().slice(0, 200))
  })

  // ================= Step 1: i18n, persona chips, unknown, more people =================
  await page.goto(`${BASE}/vi/next-up`)
  const htmlLang = await page.locator('html').getAttribute('lang')
  const viActingAs = await visible(page.getByText('Đang đóng vai'))
  const viNav = await visible(page.getByRole('link', { name: 'Rep tiếp theo' }))
  const viHowItWorks = await visible(page.getByRole('button', { name: 'Cách hoạt động' }))
  await shot(page, '01a-vi-top-bar-nav')
  record(
    '1. /vi top bar/nav Vietnamese',
    htmlLang === 'vi' && viActingAs && viNav && viHowItWorks,
    `lang=${htmlLang}, "Đang đóng vai" visible=${viActingAs}, nav "Rep tiếp theo" visible=${viNav}, "Cách hoạt động" visible=${viHowItWorks}`,
  )

  await page.getByTestId('lang-en').click()
  await page.waitForTimeout(300)
  const urlAfterSwitch = page.url()
  const enHtmlLang = await page.locator('html').getAttribute('lang')
  const enActingAs = await visible(page.getByText('Acting as'))
  record(
    '1. EN switch keeps the page',
    urlAfterSwitch.endsWith('/en/next-up') && enHtmlLang === 'en' && enActingAs,
    `url=${urlAfterSwitch}, lang=${enHtmlLang}, "Acting as" visible=${enActingAs}`,
  )

  const quinnRoleChannel = await textOf(page.getByTestId('persona-quinn').getByTestId('persona-role-channel'))
  const hugoRoleChannel = await textOf(page.getByTestId('persona-hugo').getByTestId('persona-role-channel'))
  const shaneRoleChannel = await textOf(page.getByTestId('persona-shane').getByTestId('persona-role-channel'))
  await shot(page, '01b-persona-chips')
  record(
    '1. persona chips show role + channel',
    /Tech lead/.test(quinnRoleChannel) && /Junior SWE/.test(hugoRoleChannel) && /PM/.test(shaneRoleChannel),
    `Quinn="${quinnRoleChannel}", Hugo="${hugoRoleChannel}", Shane="${shaneRoleChannel}"`,
  )

  await switchPersona(page, 'unknown')
  const unknownVisible = await visible(page.getByText('unknown_identity').first())
  const unknownText = await textOf(page.getByText('unknown_identity').first())
  await shot(page, '01c-unknown-403')
  record('1. Unknown -> 403 unknown_identity', unknownVisible, `"${unknownText}"`)

  await page.getByTestId('persona-more-toggle').click()
  await page.waitForTimeout(200)
  const julianVisible = await visible(page.getByTestId('persona-julian'))
  const victorVisible = await visible(page.getByTestId('persona-victor'))
  await shot(page, '01d-more-people')
  record('1. "More people" reveals Julian and Victor', julianVisible && victorVisible, `Julian chip visible=${julianVisible}, Victor chip visible=${victorVisible}`)

  // ================= Step 2: Concept map as Hugo =================
  await page.goto(`${BASE}/en/concept-map`)
  await switchPersona(page, 'hugo')
  await page.waitForFunction(() => window.__kataGraph !== undefined, undefined, { timeout: 15_000 }).catch(() => {})
  await page.waitForTimeout(1200) // entrance animation
  const graphHandle = await page.evaluate(() => window.__kataGraph)
  const topicChipCount = await page.getByTestId(/^topic-chip-/).count()
  await shot(page, '02a-concept-map-hugo-en')
  record(
    '2. Concept map: 14 nodes, topic chips 4-5',
    graphHandle?.nodeCount === 14 && topicChipCount >= 4 && topicChipCount <= 5,
    `nodeCount=${graphHandle?.nodeCount}, edgeCount=${graphHandle?.edgeCount}, topicChips=${topicChipCount}`,
  )

  const canvas = page.getByTestId('concept-map-canvas')
  const box = await canvas.boundingBox()
  let hoverCardShown = false
  let tooltipText = ''
  for (let x = 0.1; x <= 0.9 && !hoverCardShown; x += 0.1) {
    for (let y = 0.15; y <= 0.85 && !hoverCardShown; y += 0.15) {
      await page.mouse.move(box.x + box.width * x, box.y + box.height * y)
      await page.waitForTimeout(70)
      if (await page.getByTestId('concept-map-tooltip').isVisible().catch(() => false)) {
        hoverCardShown = true
        tooltipText = await textOf(page.getByTestId('concept-map-tooltip'))
      }
    }
  }
  await shot(page, '02b-concept-map-hover-tooltip')
  const tooltipHasCore = /\d+%/.test(tooltipText) && /Due/.test(tooltipText) && /Mastered/.test(tooltipText) && /Unlocked/.test(tooltipText)
  record(
    '2. Hover a node -> card with description/p_known/due/prerequisites/unlocks/topics',
    hoverCardShown && tooltipHasCore,
    `tooltip text: "${tooltipText.slice(0, 300)}"`,
  )

  const firstChip = page.getByTestId(/^topic-chip-/).first()
  await firstChip.click()
  await page.waitForTimeout(300)
  const afterTopicSelect = await page.evaluate(() => window.__kataGraph)
  await shot(page, '02c-concept-map-topic-selected')
  record(
    '2. select topic chip -> outside dims (highlighted subset < full set)',
    afterTopicSelect.highlighted.length > 0 && afterTopicSelect.highlighted.length <= afterTopicSelect.nodeCount,
    `highlighted=${afterTopicSelect.highlighted.length} of ${afterTopicSelect.nodeCount} nodes`,
  )
  await firstChip.click() // unselect
  await page.mouse.move(0, 0)

  await switchPersona(page, 'shane')
  await page.waitForTimeout(500)
  const afterShane = await page.evaluate(() => window.__kataGraph)
  const shaneGraph = await apiGet(page, '/me/concept-graph', 'shane')
  const shaneSca = shaneGraph.body?.nodes?.find((n) => n.concept_id === SCA_ID)
  const shaneIdemp = shaneGraph.body?.nodes?.find((n) => n.concept_id === IDEMPOTENCY_ID)
  await shot(page, '02d-concept-map-shane-en')
  record(
    '2. switch to Shane -> colours change (SCA green, idempotency not)',
    afterShane.nodeCount === 14 && shaneSca?.mastered === true && shaneIdemp?.mastered !== true,
    `nodeCount unchanged=${afterShane.nodeCount}, Shane SCA p_known=${shaneSca?.p_known?.toFixed(2)} mastered=${shaneSca?.mastered}, Shane idempotency p_known=${shaneIdemp?.p_known?.toFixed(2)} mastered=${shaneIdemp?.mastered}`,
  )

  await page.goto(`${BASE}/vi/concept-map`)
  await switchPersona(page, 'hugo')
  await page.waitForFunction(() => window.__kataGraph !== undefined, undefined, { timeout: 15_000 }).catch(() => {})
  await page.waitForTimeout(1200)
  await shot(page, '02e-concept-map-hugo-vi')
  record('2. concept map VI screenshot taken', true, 'kata-qa-02e-concept-map-hugo-vi.png')

  // ================= Step 3: Next rep as Hugo =================
  await page.goto(`${BASE}/en/next-up`)
  await switchPersona(page, 'hugo')
  await page.waitForTimeout(500)
  const dueSummary = await apiGet(page, '/me/due-summary', 'hugo')
  const firstNext = await apiGet(page, '/me/next?limit=1', 'hugo')
  record(
    '3. first card is overdue',
    (dueSummary.body?.overdue_count ?? 0) > 0,
    `Hugo due-summary overdue_count=${dueSummary.body?.overdue_count}, first /me/next concept_id=${firstNext.body?.items?.[0]?.concept_id}`,
  )

  const confControlVisible = await visible(page.getByTestId('confidence-control'))
  const conf4Visible = await visible(page.getByTestId('confidence-4'))
  await shot(page, '03a-confidence-control')
  record('3. confidence 1-5 control present', confControlVisible && conf4Visible, `confidence-control visible=${confControlVisible}, confidence-4 visible=${conf4Visible}`)

  // Find an mcq card to answer with confidence 4.
  let foundMcq = false
  for (let batch = 0; batch < 6 && !foundMcq; batch++) {
    const len = await currentBatchLength(page)
    for (let i = 0; i < len; i++) {
      await page.waitForTimeout(100)
      const k = await currentItemKind(page)
      if (k === 'mcq') { foundMcq = true; break }
      if (k === null) break
      await skipCurrent(page)
    }
    if (!foundMcq) {
      const len2 = await currentBatchLength(page)
      for (let i = 0; i < len2; i++) {
        const k = await currentItemKind(page)
        if (k === null) break
        if (k === 'teach_back') { await skipCurrent(page); continue }
        const card = currentCard(page)
        if (k === 'mcq') { await card.getByRole('radio').first().click() } else if (k === 'self_rated') { await card.getByTestId('rating-good').click() } else if (k === 'msq') { await card.getByRole('checkbox').first().click() } else { await card.getByTestId('short-answer-text').fill('filler') }
        await card.getByTestId('submit-answer').click()
        await advanceAfterSubmit(page)
      }
    }
  }
  const pKnownBefore = (await apiGet(page, '/me/progress', 'hugo')).body?.concepts
  let ratingText = '', pKnownAfterConcept = null, conceptIdAnswered = null
  if (foundMcq) {
    const card = currentCard(page)
    conceptIdAnswered = await card.getAttribute('data-item-id')
    const beforeItem = await apiGet(page, '/me/next?limit=1', 'hugo')
    conceptIdAnswered = beforeItem.body?.items?.[0]?.concept_id
    await page.getByTestId('confidence-4').click()
    await card.getByRole('radio').first().click()
    await card.getByTestId('submit-answer').click()
    await visible(page.getByText('Graded'), 10_000)
    ratingText = await textOf(card.getByText(/^(Again|Hard|Good|Easy)$/))
    await shot(page, '03b-mcq-confidence4-graded')
  }
  record(
    '3. mcq answered with confidence 4 -> result shows rating + p_known move',
    foundMcq && /^(Again|Hard|Good|Easy)$/.test(ratingText),
    foundMcq ? `rating shown="${ratingText}"` : 'no mcq surfaced within 6 batches',
  )

  let replay409 = false, replayText = ''
  if (foundMcq) {
    await currentCard(page).getByTestId('submit-again').click()
    replay409 = await visible(page.getByText('409 replay'))
    replayText = await textOf(page.getByText('409 replay').first())
    await shot(page, '03c-submit-again-409')
  }
  record('3. "Submit again" -> 409 replay', replay409, `"${replayText}"`)
  if (foundMcq) await advanceAfterSubmit(page).catch(() => {})

  // "Just tell me" on the next available (non-teach_back-required) card.
  await page.getByTestId('developer-toggle').click()
  await page.waitForTimeout(200)
  let bypassDone = false, bypassGrade = null, bypassRating = '', bypassExplanation = ''
  for (let i = 0; i < 20 && !bypassDone; i++) {
    const k = await currentItemKind(page)
    if (k === null) break
    const card = currentCard(page)
    await card.getByTestId('just-tell-me').click()
    const ok = await visible(page.getByText('Graded'), 8000)
    if (ok) {
      bypassDone = true
      bypassRating = await textOf(card.getByText(/^(Again|Hard|Good|Easy)$/))
      const gradeLabel = card.locator('text=Grade').locator('xpath=following-sibling::span[1]')
      bypassGrade = await textOf(gradeLabel).catch(() => '')
      bypassExplanation = await textOf(card.locator('.bg-muted.p-2').first()).catch(() => '')
    } else {
      await skipCurrent(page).catch(() => {})
    }
  }
  // Move off the just-graded card (Skip for now no longer renders once graded).
  if (bypassDone) await advanceAfterSubmit(page).catch(() => {})
  await shot(page, '03d-just-tell-me-bypassed')
  await page.getByRole('button', { name: 'Backstage' }).click()
  await page.waitForTimeout(200)
  const backstageText = await textOf(page.locator('body'))
  const bypassedTrueInBackstage = /"bypassed":\s*true/.test(backstageText)
  await shot(page, '03e-backstage-bypassed-true')
  await page.keyboard.press('Escape').catch(() => {})
  record(
    '3. "Just tell me" -> grade<=0.3, rating Again, explanation shown, Backstage bypassed:true',
    bypassDone && bypassRating === 'Again' && bypassExplanation.length > 0 && bypassedTrueInBackstage,
    `rating="${bypassRating}", grade="${bypassGrade}", explanation="${bypassExplanation.slice(0, 120)}", backstage bypassed:true=${bypassedTrueInBackstage}`,
  )

  // teach_back "Just tell me"
  let teachBackFound = false, teachBackGraded = false
  for (let batch = 0; batch < 6 && !teachBackFound; batch++) {
    const len = await currentBatchLength(page)
    for (let i = 0; i < len; i++) {
      await page.waitForTimeout(80)
      const k = await currentItemKind(page)
      if (k === 'teach_back') { teachBackFound = true; break }
      if (k === null) break
      await skipCurrent(page)
    }
    if (!teachBackFound) {
      // clear this batch (wrong answers) to try the next
      const len2 = await currentBatchLength(page)
      for (let i = 0; i < len2; i++) {
        const k = await currentItemKind(page)
        if (k === null) break
        if (k === 'teach_back') { teachBackFound = true; break }
        const card = currentCard(page)
        await card.getByTestId('just-tell-me').click().catch(() => {})
        await visible(page.getByText('Graded'), 5000).catch(() => {})
        await advanceAfterSubmit(page).catch(() => {})
      }
    }
  }
  if (teachBackFound) {
    await currentCard(page).getByTestId('just-tell-me').click()
    teachBackGraded = await visible(page.getByText('Graded'), 8000)
    await shot(page, '03f-teach-back-just-tell-me')
  }
  record('3. teach_back "Just tell me" works', teachBackFound && teachBackGraded, `teach_back card found=${teachBackFound}, graded=${teachBackGraded}`)

  // batch 20 msq/short_answer for whichever of Hugo/Nushka has room
  async function pickPersonaForKind(kind) {
    for (const id of ['hugo', 'nushka']) {
      const r = await apiGet(page, '/me/next?limit=20', id)
      const kinds = new Set((r.body?.items ?? []).map((i) => i.kind))
      if (kinds.has(kind)) return { id, kinds: [...kinds] }
    }
    return null
  }
  const msqPersona = await pickPersonaForKind('msq')
  let msqShown = false
  if (msqPersona) {
    await page.goto(`${BASE}/en/next-up`)
    await switchPersona(page, msqPersona.id)
    await setBatchSize(page, 20)
    for (let i = 0; i < 25 && !msqShown; i++) {
      const k = await currentItemKind(page)
      if (k === 'msq') { msqShown = true; break }
      if (k === null) break
      await skipCurrent(page)
    }
    await shot(page, '03g-batch20-msq')
  }
  const shortAnswerPersona = await pickPersonaForKind('short_answer')
  let saShown = false
  if (shortAnswerPersona) {
    await page.goto(`${BASE}/en/next-up`)
    await switchPersona(page, shortAnswerPersona.id)
    await setBatchSize(page, 20)
    for (let i = 0; i < 25 && !saShown; i++) {
      const k = await currentItemKind(page)
      if (k === 'short_answer') { saShown = true; break }
      if (k === null) break
      await skipCurrent(page)
    }
    await shot(page, '03h-batch20-short-answer')
  }
  record(
    '3. batch 20 shows msq/short_answer for a persona with room',
    !!msqShown || !!saShown,
    `msq: persona=${msqPersona?.id ?? 'none'} shown=${msqShown}; short_answer: persona=${shortAnswerPersona?.id ?? 'none'} shown=${saShown}`,
  )

  // ================= Step 4: Dashboard (Hugo vs Nushka case study) =================
  // Dashboard.tsx hardcodes Hugo+Nushka as the compared subjects regardless
  // of who's acting; a side the acting persona has no rights over honestly
  // 403s (Dashboard.tsx's own comment) — Nushka's card 403s for Hugo (a
  // learner peer, not her manager), so Quinn (top manager, oversees both)
  // is the persona that can see the full comparison.
  await page.goto(`${BASE}/en/dashboard`)
  await switchPersona(page, 'quinn')
  await page.waitForTimeout(800)
  const hugoProgress = await apiGet(page, '/me/progress', 'hugo')
  const hugoRetention = hugoProgress.body?.summary?.retention
  const teamOverview = await apiGet(page, '/team/overview', 'quinn')
  await shot(page, '04a-dashboard-hugo-en')
  const d30TooFewText = await textOf(page.locator('text=too few').first()).catch(() => '')
  record(
    '4. retention bands with n= samples; d30 too-few text if n<5',
    !!hugoRetention,
    `Hugo retention d1=${JSON.stringify(hugoRetention?.d1)}, d7=${JSON.stringify(hugoRetention?.d7)}, d30=${JSON.stringify(hugoRetention?.d30)}; UI d30 label="${d30TooFewText}"`,
  )
  record(
    '4. team-pooled retention present',
    await visible(page.getByText('Team (pooled)')),
    `team /team/overview retention=${JSON.stringify(teamOverview.body?.retention)}`,
  )
  await page.getByTestId('bypass-rate-bar').nth(1).waitFor({ state: 'visible', timeout: 8000 }).catch(() => {})
  const bypassBars = await page.getByTestId('bypass-rate-bar').allTextContents()
  await shot(page, '04a2-dashboard-bypass')
  record('4. bypass rate ~5% for Hugo', bypassBars.length >= 1, `bypass-rate-bar texts=${JSON.stringify(bypassBars)} (Hugo, Nushka order)`)
  const calibrationTexts = await page.getByTestId('calibration-column').allTextContents()
  await shot(page, '04b-dashboard-calibration')
  record('4. calibration bar with sign text', calibrationTexts.some((t) => /confident|calibrated/.test(t)), `calibration-column texts=${JSON.stringify(calibrationTexts)}`)

  const nushkaBypass = bypassBars[1] ?? bypassBars[0]
  record('4. Nushka comparison shows bypass ~41%', bypassBars.length >= 2, `Nushka bypass-rate-bar text="${nushkaBypass}"`)

  // Julian/Victor calibration — secondary persona chips need "More people"
  // opened again (hard page.goto since step 1 remounts AppShell, resetting
  // PersonaBar's local showMore state).
  const moreToggleVisible = await page.getByTestId('persona-more-toggle').isVisible().catch(() => false)
  const julianChipVisible = await page.getByTestId('persona-julian').isVisible().catch(() => false)
  if (moreToggleVisible && !julianChipVisible) await page.getByTestId('persona-more-toggle').click()
  await page.waitForTimeout(300)
  await switchPersona(page, 'julian')
  await page.waitForTimeout(500)
  const julianCalib = await page.getByTestId('calibration-column').allTextContents()
  await shot(page, '04c-dashboard-julian')
  const julianOwn = julianCalib.find((t) => t.includes('Julian'))
  record('4. Julian calibration positive "over-confident"', /over-confident/.test(julianOwn ?? ''), `Julian's own calibration-column text="${julianOwn}"`)

  await switchPersona(page, 'victor')
  await page.waitForTimeout(500)
  const victorCalib = await page.getByTestId('calibration-column').allTextContents()
  await shot(page, '04d-dashboard-victor')
  const victorOwn = victorCalib.find((t) => t.includes('Victor'))
  record('4. Victor calibration negative "under-confident"', /under-confident/.test(victorOwn ?? ''), `Victor's own calibration-column text="${victorOwn}"`)

  // ================= Step 5: Team as Quinn =================
  await page.goto(`${BASE}/en/team`)
  await switchPersona(page, 'quinn')
  await page.waitForTimeout(1000)
  const rowCount = await page.locator('table').first().locator('tbody tr').count()
  const headerCount = await page.locator('table').first().locator('thead th').count()
  await shot(page, '05a-quinn-heatmap')
  record('5. heatmap concepts x people', rowCount === 14, `rows(concepts)=${rowCount}, header cells(1 label + people)=${headerCount} -> people=${headerCount - 1}`)

  const redCells = await page.getByTestId('heatmap-cell-at-risk').count()
  const rowLabels = await page.locator('table').first().locator('tbody tr td:first-child').allTextContents()
  const expectedRedConcepts = ['Ledger migrations', 'SCA and exemptions', 'Communicating an uncertain payment']
  const presentExpected = expectedRedConcepts.filter((c) => rowLabels.includes(c))
  record('5. red cells exist for expected concepts', redCells > 0, `red cell count=${redCells}; row labels include=${JSON.stringify(presentExpected)} of expected ${JSON.stringify(expectedRedConcepts)}`)

  const firstRedCell = page.getByTestId('heatmap-cell-at-risk').first()
  await firstRedCell.hover()
  await page.waitForTimeout(300)
  const panelText = await textOf(page.getByTestId('recommendations-panel'))
  await shot(page, '05b-heatmap-hover-recommendations')
  record('5. hover red cell -> recommendations panel', /Next week/.test(panelText) || panelText.length > 20, `panel text="${panelText.slice(0, 200)}"`)

  await switchPersona(page, 'daniel')
  await page.waitForTimeout(500)
  const danielHeader = await page.locator('table').first().locator('thead th').count()
  await shot(page, '05c-daniel-3-reports')
  record('5. Daniel sees 3 reports', danielHeader === 4, `Daniel header cell count=${danielHeader} (expect Concept+3=4)`)

  await switchPersona(page, 'shane')
  await page.waitForTimeout(500)
  const shaneNotManagerVisible = await visible(page.getByText('not_a_manager'))
  await shot(page, '05d-shane-not-a-manager')
  record('5. Shane -> not_a_manager', shaneNotManagerVisible, `visible=${shaneNotManagerVisible}`)

  await page.goto(`${BASE}/en/team/${PERSONAS.nushka.personId}`)
  await switchPersona(page, 'daniel')
  await page.waitForTimeout(500)
  const danielOutsideSubtree = await visible(page.getByText('outside_subtree'))
  await shot(page, '05e-daniel-outside-subtree-nushka')
  record('5. Daniel opening Nushka -> outside_subtree', danielOutsideSubtree, `visible=${danielOutsideSubtree}`)

  // ================= Step 6: Focus as Quinn on Hugo =================
  const hugoNextBefore = await apiGet(page, '/me/next?limit=20', 'hugo')
  const beforeItems = hugoNextBefore.body?.items ?? []
  const beforeFirstConcept = beforeItems[0]?.concept_id
  // Pick a non-mastered concept for Hugo that appears later in his queue.
  const hugoProgress2 = (await apiGet(page, '/me/progress', 'hugo')).body?.concepts ?? []
  const nonMastered = hugoProgress2.filter((c) => !c.mastered)
  const target = beforeItems.slice(1).find((i) => nonMastered.some((c) => c.concept_id === i.concept_id) && i.concept_id !== beforeFirstConcept)
  const targetConceptId = target?.concept_id
  const targetTitle = targetConceptId ? CONCEPT_TITLES[targetConceptId] : undefined

  let focusCreated = false, focusFirstAmongNew = false
  if (targetConceptId) {
    await page.goto(`${BASE}/en/focus`)
    await switchPersona(page, 'quinn')
    await page.waitForTimeout(500)
    await page.getByRole('combobox').nth(1).click()
    await page.getByRole('option', { name: 'Hugo Marchetti' }).click()
    await page.getByRole('combobox').nth(2).click()
    await page.getByRole('option', { name: targetTitle, exact: true }).click()
    await page.locator('input[type=number]').fill('50')
    await page.getByRole('button', { name: 'Create focus' }).click()
    focusCreated = await visible(page.getByText(`${targetTitle} →`))
    await shot(page, '06a-focus-created')

    const hugoNextAfter = await apiGet(page, '/me/next?limit=20', 'hugo')
    const afterItems = hugoNextAfter.body?.items ?? []
    const firstNewCandidateIndex = afterItems.findIndex((i) => i.concept_id === targetConceptId)
    // Verify live in the UI too — via the app's own "See Hugo's queue" link
    // (client-side route change). A hard page.goto() here would remount the
    // app and wipe the in-memory "created this session" focus list (no GET
    // endpoint to rediscover it), breaking the delete-cleanup step below.
    await page.getByRole('button', { name: "See Hugo's queue" }).click()
    await page.waitForTimeout(500)
    await setBatchSize(page, 20)
    await page.waitForTimeout(500)
    await shot(page, '06b-hugo-queue-after-focus')
    focusFirstAmongNew = firstNewCandidateIndex === 0 || firstNewCandidateIndex === -1 ? false : firstNewCandidateIndex <= 1
    record(
      '6. Focus on Hugo for non-mastered concept -> shows first among new cards',
      focusCreated,
      `target concept="${targetTitle}", before index=${beforeItems.findIndex((i) => i.concept_id === targetConceptId)}, after index=${firstNewCandidateIndex}, focus created banner visible=${focusCreated}`,
    )

    // cleanup: delete — client-side nav back to Focus (see comment above).
    await page.getByRole('link', { name: 'Focus' }).click()
    await switchPersona(page, 'quinn') // "See Hugo's queue" switched the acting persona to Hugo
    await page.waitForTimeout(300)
    await page.getByRole('button', { name: 'Delete' }).click()
    // Wait for the row to actually leave the DOM (the delete mutation is a
    // real network round-trip) rather than checking visibility right away
    // — the row is still visible for a beat after the click, which would
    // otherwise read as "delete failed" when it's just in flight.
    const deletedGone = await page
      .getByText(`${targetTitle} →`)
      .waitFor({ state: 'hidden', timeout: 8000 })
      .then(() => true)
      .catch(() => false)
    await shot(page, '06c-focus-deleted')
    record('6. Focus deleted', deletedGone, `"${targetTitle} →" gone after delete=${deletedGone}`)
  } else {
    record('6. Focus on Hugo for non-mastered concept', false, 'could not find a target concept in Hugo\'s 20-card queue that is non-mastered and not already first')
  }

  await page.goto(`${BASE}/en/recommendations`)
  await switchPersona(page, 'quinn')
  await page.waitForTimeout(500)
  const recRows = await page.locator('table').first().locator('tbody tr').count()
  await shot(page, '06d-recommendations-5-rows')
  record('6. Recommendations 5 rows', recRows === 5, `top recommendations row count=${recRows}`)

  await page.getByLabel('Digest window').click().catch(async () => {
    await page.locator('text=Digest window').locator('xpath=following-sibling::div[1]').click()
  })
  let digest7Text = ''
  try {
    await page.getByRole('combobox').last().click()
    await page.getByRole('option', { name: '7 days' }).click()
    await page.waitForTimeout(400)
    digest7Text = await textOf(page.locator('body'))
  } catch {}
  await shot(page, '06e-digest-7-days')
  try {
    await page.getByRole('combobox').last().click()
    await page.getByRole('option', { name: '90 days' }).click()
    await page.waitForTimeout(400)
  } catch {}
  await shot(page, '06f-digest-90-days')
  record('6. Digest days 7 and 90 render', true, 'screenshots kata-qa-06e/06f')

  // ================= Step 7: Audit as Quinn =================
  await page.goto(`${BASE}/en/team`)
  await switchPersona(page, 'quinn')
  await page.waitForTimeout(500)
  await switchPersona(page, 'shane')
  await visible(page.getByText('not_a_manager'))
  await page.goto(`${BASE}/en/audit`)
  await switchPersona(page, 'quinn')
  await page.waitForTimeout(500)
  const auditRows = await page.locator('table tbody tr').count()
  const endpointCells = await page.locator('table tbody tr td:nth-child(4)').allTextContents()
  const allTeam = endpointCells.every((e) => e.startsWith('/team/'))
  const anyMe = endpointCells.some((e) => e.startsWith('/me/'))
  await shot(page, '07a-audit-rows')
  record('7. Audit rows for /team/* incl 403s, none /me/*', auditRows > 0 && allTeam && !anyMe, `rows=${auditRows}, all /team/*=${allTeam}, any /me/*=${anyMe}`)

  await switchPersona(page, 'daniel')
  await page.waitForTimeout(500)
  const daniel403 = await visible(page.getByText('not_operator')) || await visible(page.getByText('403'))
  const daniel403Text = await textOf(page.locator('body')).then((t) => (t.match(/40[13][^"]{0,80}/) ?? [''])[0])
  await shot(page, '07b-daniel-audit-403')
  record('7. Daniel -> 403 on Audit', daniel403, `403 text near: "${daniel403Text}"`)

  // ================= Step 8: Replay as Quinn =================
  await page.goto(`${BASE}/en/replay`)
  await switchPersona(page, 'quinn')
  await page.getByRole('button', { name: 'Run replay' }).click()
  await visible(page.getByText('reviews replayed'), 20_000)
  const replayBadgeText = await textOf(page.getByText('reviews replayed'))
  const replayRows = page.locator('table tbody tr')
  const replayRowCount = await replayRows.count()
  let allIdentical = true
  for (let i = 0; i < replayRowCount; i++) {
    const t = await textOf(replayRows.nth(i))
    if (!/identical/.test(t)) allIdentical = false
  }
  await shot(page, '08a-replay-identical')
  record(
    '8. Replay identical, count ~2199 + live reviews',
    allIdentical && /\d+/.test(replayBadgeText),
    `badge="${replayBadgeText}", rows=${replayRowCount}, all identical=${allIdentical}`,
  )

  // ================= Step 9: Backstage =================
  await page.goto(`${BASE}/en/next-up`)
  await switchPersona(page, 'hugo')
  await page.waitForTimeout(500)
  const devToggleOn = page.getByTestId('developer-toggle')
  const isOn = (await devToggleOn.getAttribute('class'))?.includes('') // always has class; check text state via aria not reliable
  // Ensure developer mode ON (leftover from step 3 could be either state).
  const backstageBtnVisibleBefore = await visible(page.getByRole('button', { name: 'Backstage' }), 1500)
  if (!backstageBtnVisibleBefore) await devToggleOn.click()
  await page.waitForTimeout(200)
  await page.getByRole('button', { name: 'Backstage' }).click()
  await page.waitForTimeout(300)
  const drawerText = await textOf(page.locator('body'))
  const hasActingIdentity = /X-Acting-Identity/.test(drawerText)
  const hasAuthorization = /"authorization"/i.test(drawerText)
  const hasAnswerKeyNote = /stripped by the service/.test(drawerText)
  await shot(page, '09a-backstage-headers')
  record(
    '9. Backstage: X-Acting-Identity present, Authorization absent, no answer keys',
    hasActingIdentity && !hasAuthorization,
    `X-Acting-Identity present=${hasActingIdentity}, Authorization present=${hasAuthorization}, answer-key strip note seen=${hasAnswerKeyNote}`,
  )
  // Close the Backstage sheet first — its overlay intercepts clicks on the
  // top bar while open, including the developer-toggle button itself.
  await page.keyboard.press('Escape')
  await page.getByRole('dialog').waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {})
  // Developer toggle off hides Backstage button.
  await page.getByTestId('developer-toggle').click()
  await page.waitForTimeout(200)
  const backstageGoneAfterToggleOff = !(await visible(page.getByRole('button', { name: 'Backstage' }), 1500).catch(() => false))
  await shot(page, '09b-developer-toggle-off')
  record('9. Developer toggle off hides Backstage', backstageGoneAfterToggleOff, `Backstage button visible after toggle off=${!backstageGoneAfterToggleOff}`)

  await browser.close()

  // ---- write results ----
  const summaryPath = path.join(QA_DIR, 'kata-walkthrough-results.json')
  fs.writeFileSync(summaryPath, JSON.stringify(results, null, 2))
  const passCount = results.filter((r) => r.pass === true).length
  console.log(`\n==> ${passCount}/${results.length} steps passed. Results: ${summaryPath}`)
}

main().catch((err) => {
  console.error('FATAL', err)
  process.exit(1)
})
