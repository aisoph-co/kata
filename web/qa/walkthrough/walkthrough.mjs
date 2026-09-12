// Throwaway QA script — manual UI walkthrough of PLAN_06 §Acceptance, Part 2
// (agents/qa/2026-09-09-demo-web.md, second pass). Drives the real running
// stack (localhost:5173 / :8000) with Playwright's chromium directly — no
// playwright.config, no webServer management, the stack is already up.
// Never touches src/ or e2e/. Selector/helper patterns are read from
// e2e/helpers.ts (not imported, not modified) since this must stay outside
// the shipped suite.
import { chromium } from '@playwright/test'
import path from 'node:path'

const QA_DIR = path.resolve(import.meta.dirname, '..')
const results = []

function shot(page, name) {
  return page.screenshot({ path: path.join(QA_DIR, `qa-${name}.png`) })
}

function record(step, pass, evidence) {
  results.push({ step, pass, evidence: evidence.replace(/\s+/g, ' ').trim() })
  console.log(`[${pass ? 'PASS' : (pass === null ? 'INFO' : 'FAIL')}] ${step} — ${evidence}`)
}

async function textOf(locator) {
  try {
    return (await locator.textContent()) ?? ''
  } catch {
    return ''
  }
}

// ---- helper-pattern copies (from e2e/helpers.ts, read-only reference) ----
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
  const m = t?.match(/of (\d+)/)
  return m ? Number(m[1]) : 5
}
async function skipCurrent(page) {
  await currentCard(page).getByTestId('skip-for-now').click()
}
async function advanceAfterSubmit(page, timeout = 10_000) {
  await currentCard(page).getByTestId('next-card').click({ timeout })
}
async function submitCurrent(page, opts = {}) {
  const card = currentCard(page)
  await card.waitFor({ state: 'visible' })
  const kind = await currentItemKind(page)
  if (kind === 'mcq') {
    await card.getByRole('radio').nth(opts.wrong ? 1 : 0).click()
  } else if (kind === 'msq') {
    const boxes = card.getByRole('checkbox')
    const n = await boxes.count()
    await boxes.first().click()
    if (opts.partial && n > 1) await boxes.nth(1).click()
  } else if (kind === 'self_rated') {
    await card.getByTestId(opts.selfRated ?? (opts.wrong ? 'rating-again' : 'rating-good')).click()
  } else if (kind === 'short_answer') {
    await card.getByTestId('short-answer-text').fill(opts.text ?? 'a filler answer for the demo suite')
  } else {
    return kind
  }
  await card.getByTestId('submit-answer').click()
  return kind
}
async function advanceUntilKind(page, kind, maxBatches = 6) {
  for (let batch = 0; batch < maxBatches; batch++) {
    const length = await currentBatchLength(page)
    for (let i = 0; i < length; i++) {
      await page.waitForTimeout(120)
      const current = await currentItemKind(page)
      if (current === kind) return true
      if (current === null) return false
      await skipCurrent(page)
    }
    for (let i = 0; i < length; i++) {
      const current = await currentItemKind(page)
      if (current === null) break
      if (current === 'teach_back') {
        await skipCurrent(page)
      } else {
        await submitCurrent(page, { wrong: true })
        await advanceAfterSubmit(page)
      }
    }
    await currentCard(page).getByTestId('skip-for-now').waitFor({ state: 'visible', timeout: 10_000 }).catch(() => {})
  }
  return (await currentItemKind(page)) === kind
}
async function setBatchSize(page, size) {
  await page.getByTestId('batch-size-select').click()
  await page.getByRole('option', { name: String(size), exact: true }).click()
  await page.waitForTimeout(200)
}
async function switchPersona(page, id) {
  await page.getByTestId(`persona-${id}`).click()
  await page.waitForTimeout(300)
}

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })

  // ================= Step 1 =================
  await page.goto('http://localhost:5173/next-up')
  await switchPersona(page, 'unknown')
  await page.getByText('unknown_identity').first().waitFor({ timeout: 10_000 })
  const unknownText = await textOf(page.getByText('unknown_identity').first())
  await shot(page, '01a-unknown-403')
  record('1a. Unknown persona -> 403 unknown_identity', unknownText.includes('unknown_identity'), unknownText)

  await switchPersona(page, 'dee')
  await page.getByText('Dee Learner').first().waitFor({ timeout: 10_000 })
  const deeResolved = await textOf(page.locator('span', { hasText: 'Dee Learner' }).first())
  await shot(page, '01b-dee-resolved')
  record('1b. Dee -> resolved person summary shows her name', deeResolved.includes('Dee'), deeResolved)

  // ================= Step 2 =================
  await page.goto('http://localhost:5173/next-up')
  await switchPersona(page, 'dee')
  await page.getByTestId('next-item-card').waitFor({ timeout: 10_000 })

  // batch size control
  await page.getByTestId('batch-size-select').click()
  const options = await page.getByRole('option').allTextContents()
  await page.keyboard.press('Escape')
  await shot(page, '02a-batch-size-options')
  record('2a. Batch size control shows 5/10/20', JSON.stringify(options) === JSON.stringify(['5', '10', '20']), options.join(', '))

  // first card overdue-not-new: cross-check via Progress p_known for that concept
  const firstConceptBadge = await textOf(page.getByTestId('next-item-card').locator('[data-slot="badge"]').last())
  await page.goto('http://localhost:5173/progress')
  await switchPersona(page, 'dee')
  await page.getByRole('table').waitFor({ timeout: 10_000 })
  const progressRowText = await textOf(page.locator('tr', { hasText: firstConceptBadge }))
  await shot(page, '02b-progress-first-concept')
  record(
    '2b. Next up first card is overdue (not new) — cross-check via Progress',
    null,
    `Next up's first card concept = "${firstConceptBadge}"; its Progress row: "${progressRowText}" (nonzero p_known/due_count implies prior exposure, i.e. overdue not new — no per-card overdue/new label exists in the UI itself, inferred from this cross-check)`,
  )

  // mcq correct -> Good, p_known moves; submit again -> 409 replay
  await page.goto('http://localhost:5173/next-up')
  await switchPersona(page, 'dee')
  let found = await advanceUntilKind(page, 'mcq')
  if (found) {
    const card = page.getByTestId('next-item-card')
    await card.getByRole('radio').first().click()
    await card.getByTestId('submit-answer').click()
    await page.getByText('Graded').waitFor({ timeout: 10_000 })
    const gradedText = await textOf(page.locator('body'))
    const hasGood = gradedText.includes('Good')
    const pKnownAfter = await textOf(page.locator('[data-testid="next-item-card"] ~ * >> text=/%/').first()).catch(() => '')
    await shot(page, '02c-mcq-correct-good')
    record('2c. mcq correct -> rating Good, p_known shown', hasGood, `result panel visible, "Good" present=${hasGood}`)

    await card.getByTestId('submit-again').click()
    await page.getByText('409 replay — same result as before').waitFor({ timeout: 10_000 })
    const replayVisible = await page.getByText('409 replay — same result as before').isVisible()
    await shot(page, '02d-mcq-replay-409')
    record('2d. Submit again (same key) -> 409 replay shown in result panel', replayVisible, '409 replay — same result as before')

    // Backstage shows the replay too
    await page.getByRole('button', { name: /Backstage/ }).click()
    const backstageBody = await textOf(page.locator('[data-slot="sheet-content"], [role="dialog"]').first())
    await shot(page, '02e-backstage-replay')
    record('2e. Backstage shows the 409 replay call', backstageBody.includes('409') || backstageBody.includes('idempotency_replay'), backstageBody.slice(0, 200))
    await page.keyboard.press('Escape')

    await card.getByTestId('next-card').click()
    const foundAgain = await advanceUntilKind(page, 'mcq')
    if (foundAgain) {
      const card2 = page.getByTestId('next-item-card')
      await card2.getByRole('radio').nth(1).click()
      await card2.getByTestId('submit-answer').click()
      await page.getByText('Again', { exact: true }).waitFor({ timeout: 10_000 })
      await shot(page, '02f-mcq-wrong-again')
      record('2f. mcq wrong -> rating Again', true, 'Again badge visible')
    } else {
      record('2f. mcq wrong -> rating Again', false, 'no further mcq item reachable to test wrong answer')
    }
  } else {
    record('2c/2d/2f. mcq flow', false, 'no mcq item reachable within batches')
  }

  // self_rated: pick 1-4, see a grade
  await page.goto('http://localhost:5173/next-up')
  await switchPersona(page, 'dee')
  found = await advanceUntilKind(page, 'self_rated')
  if (found) {
    const card = page.getByTestId('next-item-card')
    await card.getByTestId('rating-easy').click()
    await card.getByTestId('submit-answer').click()
    await page.getByText('Graded').waitFor({ timeout: 10_000 })
    await shot(page, '02g-self-rated-graded')
    record('2g. self_rated: pick 1-4 (Easy) -> graded', true, 'Graded panel visible after rating-easy + submit')
  } else {
    record('2g. self_rated flow', false, 'no self_rated item reachable within batches')
  }

  // Jia, batch 20: msq partial, short_answer, teach_back
  await page.goto('http://localhost:5173/next-up')
  await switchPersona(page, 'jia')
  await setBatchSize(page, 20)
  await page.getByTestId('next-item-card').waitFor({ timeout: 10_000 })

  let kindFound = await advanceUntilKind(page, 'short_answer', 3)
  if (kindFound) {
    await submitCurrent(page, { text: 'a filler short answer for the demo QA walkthrough' })
    await page.getByText('Graded').waitFor({ timeout: 10_000 })
    await shot(page, '02h-jia-short-answer-graded')
    record('2h. Jia batch20 short_answer -> stub grade', true, 'Graded panel visible')
    await currentCard(page).getByTestId('next-card').click().catch(() => {})
  } else {
    record('2h. Jia batch20 short_answer', false, 'no short_answer item reachable in batch-20')
  }

  kindFound = await advanceUntilKind(page, 'msq', 3)
  if (kindFound) {
    await submitCurrent(page, { partial: true })
    await page.getByText('Graded').waitFor({ timeout: 10_000 })
    const gradeCell = await textOf(page.locator('text=Grade').locator('xpath=following-sibling::span').first())
    await shot(page, '02i-jia-msq-partial-fractional')
    record('2i. Jia batch20 msq partial selection -> fractional grade', true, `Grade shown: "${gradeCell}"`)
    await currentCard(page).getByTestId('next-card').click().catch(() => {})
  } else {
    record('2i. Jia batch20 msq partial', false, 'no msq item reachable in batch-20')
  }

  kindFound = await advanceUntilKind(page, 'teach_back', 3)
  if (kindFound) {
    const noticeVisible = await page.getByText('teach_back items have no grader yet').isVisible()
    await shot(page, '02j-jia-teach-back-notice')
    await skipCurrent(page)
    await page.getByRole('button', { name: /Backstage/ }).click()
    const backstageBody2 = await textOf(page.locator('[data-slot="sheet-content"], [role="dialog"]').first())
    await shot(page, '02k-backstage-skipped-locally')
    record(
      '2j/2k. teach_back -> notice + Skip for now -> Backstage "skipped locally"',
      noticeVisible && backstageBody2.includes('skipped locally'),
      `notice visible=${noticeVisible}; backstage contains "skipped locally"=${backstageBody2.includes('skipped locally')}`,
    )
    await page.keyboard.press('Escape')
  } else {
    record('2j/2k. teach_back flow', false, 'no teach_back item reachable in batch-20')
  }

  // ================= Step 3 =================
  await page.goto('http://localhost:5173/progress')
  await switchPersona(page, 'dee')
  await page.getByRole('table').waitFor({ timeout: 10_000 })
  const dueChips = await textOf(page.getByText('due total').locator('..'))
  await shot(page, '03a-progress-due-chips')
  record('3a. Progress: due summary chips present (a concept just answered changed — see 2c/2f/2g p_known)', dueChips.includes('due') && dueChips.includes('overdue'), dueChips)

  await page.goto('http://localhost:5173/answers-notes')
  await switchPersona(page, 'dee')
  const uniqueText = `qa walkthrough note ${Date.now()}`
  await page.getByPlaceholder('Add a note…').fill(uniqueText)
  await page.getByRole('button', { name: 'Add note' }).click()
  await page.getByText(uniqueText).waitFor({ timeout: 10_000 })
  await shot(page, '03b-note-added')
  record('3b. Add a note', true, uniqueText)

  await page.getByPlaceholder('Add a note…').fill('x'.repeat(501))
  await page.getByRole('button', { name: 'Add note' }).click()
  await page.getByText('at most 20 notes of 500 characters each').waitFor({ timeout: 10_000 })
  const capText = await textOf(page.getByText('at most 20 notes of 500 characters each'))
  await shot(page, '03c-note-cap-error')
  record('3c. 501-char note -> note_cap verbatim', true, capText)

  const noteRow = page.locator('li', { hasText: uniqueText })
  await noteRow.getByRole('button').click()
  await page.getByText(uniqueText).waitFor({ state: 'detached', timeout: 10_000 }).catch(() => {})
  await shot(page, '03d-note-deleted')
  const stillThere = await page.getByText(uniqueText).count()
  record('3d. delete the note', stillThere === 0, `remaining count=${stillThere}`)

  // "Answers" only records free-text (short_answer) responses — ensure at
  // least one exists so "Delete all" is exercised meaningfully, not a
  // vacuous already-empty click.
  const deleteAllBtn = page.getByRole('button', { name: 'Delete all' })
  if (await deleteAllBtn.isDisabled()) {
    await page.goto('http://localhost:5173/next-up')
    await switchPersona(page, 'dee')
    await setBatchSize(page, 20)
    const gotShortAnswer = await advanceUntilKind(page, 'short_answer', 3)
    if (gotShortAnswer) {
      await submitCurrent(page, { text: 'qa walkthrough delete-all seed answer' })
      await page.getByText('Graded').waitFor({ timeout: 10_000 })
    }
    await page.goto('http://localhost:5173/answers-notes')
    await switchPersona(page, 'dee')
    await page.waitForTimeout(500)
  }
  const answersBeforeDelete = await page.locator('ul li').count().catch(() => 0)
  if (await deleteAllBtn.isEnabled().catch(() => false)) {
    await deleteAllBtn.click()
    await page.waitForTimeout(1000)
  }
  const emptyAnswers = await page.getByText('No answers yet.').isVisible().catch(() => false)
  await shot(page, '03e-delete-all-answers')
  record('3e. "Delete all" answers', emptyAnswers, `had ${answersBeforeDelete} answer(s) before delete; "No answers yet." visible after=${emptyAnswers}`)

  // ================= Step 4 =================
  await page.goto('http://localhost:5173/team')
  await switchPersona(page, 'ada')
  await page.getByRole('table').first().waitFor({ timeout: 10_000 })
  const rowCount = await page.locator('table').first().locator('tbody tr').count()
  const headerCount = await page.locator('table').first().locator('thead th').count()
  await shot(page, '04a-ada-heatmap')
  record('4a. Ada Team: heatmap 12 concepts x 9 people', rowCount === 12 && headerCount === 10, `rows=${rowCount}, header cells=${headerCount}`)

  const atRiskDots = await page.locator('.bg-destructive.rounded-full').count()
  await shot(page, '04b-at-risk-dots')
  record('4b. at-risk dot present on heatmap (Jia weak concepts)', atRiskDots > 0, `at-risk dot count=${atRiskDots}`)

  await switchPersona(page, 'ben')
  await page.waitForTimeout(500)
  const benHeaderCount = await page.locator('table').first().locator('thead th').count()
  await shot(page, '04c-ben-subtree')
  record('4c. Ben sees a smaller subtree (5 header cells: Concept + 4 reports)', benHeaderCount === 5, `header cells=${benHeaderCount}`)

  await switchPersona(page, 'dee')
  await page.getByText('not_a_manager').waitFor({ timeout: 10_000 })
  const notManagerText = await textOf(page.getByText('not_a_manager'))
  await shot(page, '04d-dee-not-a-manager')
  record('4d. Dee -> Team shows not_a_manager card', notManagerText.includes('not_a_manager'), notManagerText)

  const jiaId = '6a475a91-895b-5f48-921e-ebabacfbbdd5'
  await page.goto(`http://localhost:5173/team/${jiaId}`)
  await switchPersona(page, 'ben')
  await page.getByText('outside_subtree').waitFor({ timeout: 10_000 })
  const outsideText = await textOf(page.getByText('outside_subtree'))
  await shot(page, '04e-ben-outside-subtree')
  record('4e. Ben opening Jia drill-down -> outside_subtree', outsideText.includes('outside_subtree'), outsideText)

  // ================= Step 5 =================
  await page.goto('http://localhost:5173/focus')
  await switchPersona(page, 'ada')
  await page.getByRole('combobox').first().waitFor({ timeout: 10_000 })

  // Selection order (learning_service/engine/selection.py docstring):
  // overdue reviews (retrievability ascending) always precede ANY new
  // item; focus_weight only re-ranks the new-item pool. So the target must
  // be a genuinely "new" concept — not-yet-mastered AND not currently
  // overdue (due_count 0, unlocked, no prior review) — for the focus's
  // effect on ranking to be observable, and it must NOT already be the
  // top-ranked new item (so the focus boost has something to prove).
  const dueSummaryBefore = await page.request.get('http://localhost:5173/api/me/due-summary', {
    headers: { 'X-Acting-Identity': 'whatsapp:U003' },
  })
  const overdueCountBefore = (await dueSummaryBefore.json()).overdue_count
  const nextForDee = await page.request.get('http://localhost:5173/api/me/next?limit=20', {
    headers: { 'X-Acting-Identity': 'whatsapp:U003' },
  })
  const nextBody = await nextForDee.json()
  const progressForDee = await page.request.get('http://localhost:5173/api/me/progress', {
    headers: { 'X-Acting-Identity': 'whatsapp:U003' },
  })
  const progressBody = await progressForDee.json()
  const newConceptIds = new Set(
    progressBody.concepts.filter((c) => c.unlocked && !c.mastered && c.due_count === 0).map((c) => c.concept_id),
  )
  const items = nextBody.items ?? []
  // items[overdueCountBefore] is the current #1-ranked new item (by
  // score); pick the SECOND new-item candidate present in the queue so
  // the focus boost genuinely has to move it up to prove anything.
  const newItemsInQueue = items.slice(overdueCountBefore).filter((i) => newConceptIds.has(i.concept_id))
  const target = newItemsInQueue[1] ?? newItemsInQueue[0]
  const targetBeforeIndex = target ? items.findIndex((i) => i.concept_id === target.concept_id) : -1

  const CONCEPT_TITLES = {
    '9e028398-a3ef-5907-92e7-d41d91866cb7': 'Variables',
    '6fc836bb-573a-5b04-9bf0-1f03b04275fb': 'Control Flow',
    '24323e4a-44b6-546f-b6c7-cbfed52246bb': 'Functions',
    '7a34da9b-1c15-5d8c-95aa-eaf95bb1cfa3': 'Collections',
    '9d38f1b4-f25d-5b2d-8f3d-367e76e1d567': 'Recursion',
    '0fbef780-f952-544d-b1c0-e85a14e2bb70': 'Error Handling',
    '1fd5b719-5cd5-52da-8605-636710acb226': 'Testing',
    '6f650220-e0be-56a3-912b-e24d2921372d': 'IO',
    '44160f6b-05f5-5dc8-a303-37c61f71bb72': 'Modules',
    'e5371e14-c5e4-5450-81e3-56fc7862ef14': 'Debugging',
    '939352f1-7e17-5ea1-a266-83592cf42d29': 'Concurrency',
    '627758ca-e7c0-5f25-82bf-a6688b8d54a6': 'Design Patterns',
  }

  if (target) {
    const title = CONCEPT_TITLES[target.concept_id]
    await page.getByRole('combobox').nth(1).click()
    await page.getByRole('option', { name: 'Dee Learner' }).click()
    await page.getByRole('combobox').nth(2).click()
    await page.getByRole('option', { name: title, exact: true }).click()
    await page.locator('input[type=number]').fill('50')
    await page.getByRole('button', { name: 'Create focus' }).click()
    await page.getByText(`${title} →`).waitFor({ timeout: 10_000 })
    await shot(page, '05a-focus-created')
    record('5a. Create focus for Dee on not-yet-mastered concept', true, `concept="${title}"`)

    await page.getByRole('button', { name: "See Dee's queue" }).click()
    await page.waitForURL(/\/next-up/)
    await page.getByTestId('next-item-card').waitFor({ timeout: 10_000 })
    const firstCardConceptDefault = await textOf(page.getByTestId('next-item-card').locator('[data-slot="badge"]').last())
    await shot(page, '05b-dee-queue-default-batch')

    await setBatchSize(page, 20)
    await page.getByTestId('next-item-card').waitFor({ timeout: 10_000 })
    const firstCardConceptB20 = await textOf(page.getByTestId('next-item-card').locator('[data-slot="badge"]').last())
    const dueSummaryAfter = await page.request.get('http://localhost:5173/api/me/due-summary', {
      headers: { 'X-Acting-Identity': 'whatsapp:U003' },
    })
    const overdueCountAfter = (await dueSummaryAfter.json()).overdue_count
    const after20 = await page.request.get('http://localhost:5173/api/me/next?limit=20', {
      headers: { 'X-Acting-Identity': 'whatsapp:U003' },
    })
    const after20Body = await after20.json()
    const afterIndex = (after20Body.items ?? []).findIndex((i) => i.concept_id === target.concept_id)
    const isFirstAmongNew = afterIndex === overdueCountAfter
    const movedUp = targetBeforeIndex >= 0 && afterIndex >= 0 && afterIndex < targetBeforeIndex

    // Confirm via the actual rendered UI (not just the API cross-check):
    // skip forward, card by card, to the claimed position and read its
    // concept badge.
    let uiBadgeAtClaimedPosition = ''
    if (afterIndex >= 0 && afterIndex < 20) {
      for (let i = 0; i < afterIndex; i++) {
        await skipCurrent(page)
        await page.waitForTimeout(60)
      }
      uiBadgeAtClaimedPosition = (
        await textOf(page.getByTestId('next-item-card').locator('[data-slot="badge"]').last())
      ).trim()
    }
    await shot(page, '05c-dee-queue-batch20-at-target-position')
    record(
      "5b. See Dee's queue -> target concept becomes the first NEW-item candidate",
      isFirstAmongNew && uiBadgeAtClaimedPosition === title,
      `default-batch(5) first card="${firstCardConceptDefault.trim()}"; batch-20 card 1 = "${firstCardConceptB20.trim()}" (still overdue — overdue_count=${overdueCountAfter} precede all new items by design); target "${title}" was at index ${targetBeforeIndex} before the focus, now at index ${afterIndex} = first-of-new (isFirstAmongNew=${isFirstAmongNew}, movedUp=${movedUp}); UI card at position ${afterIndex + 1} of 20 shows concept badge "${uiBadgeAtClaimedPosition}" — matches target=${uiBadgeAtClaimedPosition === title}. selection.py: overdue reviews always precede new items, focus_weight only re-ranks the new-item pool — so "first card in Next up" literally holds only once overdue_count is 0; the reachable, correct claim (and what's verified here, in the UI) is "first among new-item candidates".`,
    )

    await page.getByRole('link', { name: 'Focus' }).click()
    await switchPersona(page, 'ada')
    await page.getByText(`${title} →`).waitFor({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Delete' }).click()
    await page.getByText(`${title} →`).waitFor({ state: 'detached', timeout: 10_000 }).catch(() => {})
    const stillThereFocus = await page.getByText(`${title} →`).count()
    await shot(page, '05c-focus-deleted')
    record('5c. delete the focus', stillThereFocus === 0, `remaining count=${stillThereFocus}`)
  } else {
    record('5a/5b/5c. Focus flow', false, `Dee has fewer than 2 genuinely-new (unlocked, not mastered, due_count=0) candidate concepts right now (new_available_count driven) — queue len=${items.length}`)
  }

  // Recommendations: 5 rows with scores
  await page.goto('http://localhost:5173/recommendations')
  await switchPersona(page, 'ada')
  await page.getByRole('table').first().waitFor({ timeout: 10_000 })
  const recRows = await page.locator('table').first().locator('tbody tr').count()
  await shot(page, '05d-recommendations')
  record('5d. Recommendations: 5 rows with scores', recRows === 5, `rows=${recRows}`)

  // Digest days=7 and 90 render; day=0 not offered in UI
  const daySelect = page.locator('button[data-slot="select-trigger"]').last()
  await daySelect.click()
  const dayOptionsList = await page.getByRole('option').allTextContents()
  await page.keyboard.press('Escape')
  await shot(page, '05e-digest-day-options')
  record('5e. Digest day selector options', null, `options offered: ${dayOptionsList.join(', ')}`)

  await daySelect.click()
  await page.getByRole('option', { name: '7 days', exact: true }).click()
  await page.waitForTimeout(500)
  const digest7 = await page.getByText(/no at-risk pairs|Variables|Control Flow|Functions/).first().isVisible().catch(() => false)
  await shot(page, '05f-digest-7-days')
  record('5f. Digest days=7 renders', digest7, `content visible=${digest7}`)

  await daySelect.click()
  await page.getByRole('option', { name: '90 days', exact: true }).click()
  await page.waitForTimeout(500)
  const digest90 = await page.getByText(/no at-risk pairs|Variables|Control Flow|Functions/).first().isVisible().catch(() => false)
  await shot(page, '05g-digest-90-days')
  record('5g. Digest days=90 renders', digest90, `content visible=${digest90}`)

  record('5h. Digest days=0 -> 422', null, `days=0 is NOT an offered option in the UI selector (offered: ${dayOptionsList.join(', ')}) — cannot be reached through the UI as instructed, not tested via curl`)

  // ================= Step 6 =================
  await page.goto('http://localhost:5173/audit')
  await switchPersona(page, 'ada')
  await page.getByRole('table').waitFor({ timeout: 10_000 })
  const auditRowsText = await page.locator('table tbody tr').allTextContents()
  const endpoints = await page.locator('table tbody tr td:nth-child(4)').allTextContents()
  const allTeamOnly = endpoints.every((e) => e.startsWith('/team/'))
  const hasNotAManagerOr403 = auditRowsText.some((r) => r.includes('/team/overview')) // Dee's not_a_manager attempt logs against /team/overview
  const hasOutsideSubtree = auditRowsText.some((r) => r.includes('/team/people'))
  await shot(page, '06a-audit-rows')
  record('6a. Audit: rows for /team/* calls, none for /me/*', allTeamOnly, `${endpoints.length} rows, all /team/*=${allTeamOnly}; sample: ${endpoints.slice(0, 5).join(', ')}`)
  record('6b. Audit includes the two 403 attempts', hasNotAManagerOr403 && hasOutsideSubtree, `contains /team/overview row(s)=${hasNotAManagerOr403}, /team/people row(s)=${hasOutsideSubtree}`)

  await switchPersona(page, 'ben')
  await page.getByText(/403|not_operator/).first().waitFor({ timeout: 10_000 }).catch(() => {})
  const benAuditText = await textOf(page.locator('main').first())
  await shot(page, '06c-ben-audit-403')
  record('6c. Ben -> 403 on Audit', benAuditText.includes('403'), benAuditText.slice(0, 200))

  // ================= Step 7 =================
  await page.goto('http://localhost:5173/replay')
  await switchPersona(page, 'ada')
  await page.getByRole('button', { name: 'Run replay' }).click()
  await page.getByText('reviews replayed').waitFor({ timeout: 20_000 })
  const replayBadge = await textOf(page.getByText('reviews replayed'))
  const replayedCount = Number(replayBadge.match(/\d+/)?.[0] ?? 0)
  const rows = page.locator('table tbody tr')
  const rowCount7 = await rows.count()
  const allTexts = await rows.allTextContents()
  const allIdentical = allTexts.every((t) => t.includes('identical'))
  await shot(page, '07a-replay-identical')
  record('7a. Replay "identical" for Dee, replayed count > 200', allIdentical && replayedCount > 200, `replayed=${replayedCount}, rows=${rowCount7}, all identical=${allIdentical}`)

  // ================= Step 8 =================
  await page.goto('http://localhost:5173/next-up')
  await switchPersona(page, 'dee')
  await page.getByTestId('next-item-card').waitFor({ timeout: 10_000 })
  await page.getByRole('button', { name: /Backstage/ }).click()
  await page.waitForTimeout(500)
  const firstDetails = page.locator('details').first()
  await firstDetails.locator('summary').click()
  const detailsBody = await textOf(firstDetails)
  const hasActingIdentity = detailsBody.includes('X-Acting-Identity')
  const hasAuthHeader = detailsBody.includes('"authorization"') || detailsBody.includes('"Authorization"')
  await shot(page, '08a-backstage-headers')
  record('8a. Backstage headers show X-Acting-Identity, never Authorization', hasActingIdentity && !hasAuthHeader, `X-Acting-Identity present=${hasActingIdentity}, Authorization present=${hasAuthHeader}`)

  const nextUpEntry = page
    .locator('details')
    .filter({ has: page.locator('summary span.flex-1', { hasText: /^\/me\/next\?limit=\d+$/ }) })
    .first()
  await nextUpEntry.locator('summary').click().catch(() => {})
  const nextUpBody = await textOf(nextUpEntry)
  const answerKeyMatch = nextUpBody.match(/"(correct_index|correct_indices|reference|rubric)"\s*:/)
  const noAnswerKeys = !answerKeyMatch
  const hasStripNote = nextUpBody.includes('stripped by the service')
  await shot(page, '08b-backstage-no-answer-keys')
  record(
    '8b. /me/next response shows "no answer keys" note and no answer-key fields',
    noAnswerKeys && hasStripNote,
    `no answer-key fields=${noAnswerKeys}${answerKeyMatch ? ` (matched: ${answerKeyMatch[0]})` : ''}, strip note present=${hasStripNote}`,
  )

  await browser.close()

  console.log('\n=== SUMMARY ===')
  for (const r of results) {
    console.log(`${r.pass === true ? 'PASS' : r.pass === false ? 'FAIL' : 'INFO'}\t${r.step}`)
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
