/**
 * Excerpts for `topic.grounded_in` source citations (KATA-14/W11). Same
 * pattern as `ferry-scenario.ts`: the web app has no runtime route to the
 * Python fixtures, so this is a baked-in copy of the same source text —
 * generated once from the vendored `1-context/` files this demo runs
 * against (`learning_service/fixtures/ferry/issues.jsonl` and
 * `sprint-history.md`; see that directory's `SOURCE.md`) — not a live read.
 *
 * Only those two files are vendored into this repo's `1-context/` snapshot,
 * so a `grounded_in` entry naming any other file (`company.md`,
 * `release-notes.md`, `repo-excerpts.md`, seen on other topics but not on
 * the `idempotent-retries` one this issue's done-check exercises) resolves
 * to `kind: 'unavailable'` rather than fabricated text.
 */

interface IssueRecord {
  key: string
  type: string
  status: string
  title: string
  body: string
  assignee: string
}

// Verbatim from learning_service/fixtures/ferry/issues.jsonl.
const ISSUES: IssueRecord[] = [
  { key: 'PAY-1841', type: 'task', status: 'done', assignee: 'daniel.okonkwo@ferry.example', title: 'Audit every retry path in orchestrator for idempotency key reuse', body: 'Three paths mint a fresh key on retry: the timeout handler, the acquirer-503 branch, and the manual replay endpoint. All three can double-charge. Full list in the thread.' },
  { key: 'PAY-1847', type: 'bug', status: 'done', assignee: 'hugo.marchetti@ferry.example', title: 'Retry attempts must share the original idempotency key', body: 'Fixes the three paths from PAY-1841. Key is now taken from the payment intent rather than generated per attempt.' },
  { key: 'PAY-1852', type: 'story', status: 'in_progress', assignee: 'hugo.marchetti@ferry.example', title: 'Cap total retry attempts and show retry state to the customer', body: "Customer currently sees nothing between attempt one and attempt three. If they re-enter a different card mid-retry they can be charged on both paths. Needs a visible 'we are retrying' state and a hard cap of 3." },
  { key: 'PAY-1859', type: 'task', status: 'in_progress', assignee: 'julian.reyes@ferry.example', title: 'Raise idempotency key TTL to 72h', body: 'TTL is 24h; the retry window with backoff can reach 26h. A retry arriving after expiry is treated as a new charge. TTL must exceed the maximum retry window by construction, with a test asserting it.' },
  { key: 'PAY-1863', type: 'task', status: 'blocked', assignee: 'yongyi.tan@ferry.example', title: 'add_posting_currency migration (REVERTED)', body: 'Reverted 8 Sep. Single-statement UPDATE locked postings for 34s in staging. Needs chunked batches, off-peak window, and a dry run against a production snapshot. Staging has 4% of production rows.' },
  { key: 'PAY-1870', type: 'story', status: 'not_started', assignee: 'shane.delaney@ferry.example', title: 'SCA exemption changes for 1 October', body: 'Low-value threshold drops; TRA exemption needs stronger evidence. Need to know which exemptions we currently claim before we can say what changes. Nobody on the engineering side can answer this.' },
  { key: 'PAY-1834', type: 'bug', status: 'done', assignee: 'daniel.okonkwo@ferry.example', title: 'Adyen refusalReasonCode not handled - 9 days of unknown declines', body: "Adyen renamed the field in August. Adapter fell through to 'unknown decline'; 1,400 payments were retried that should have been hard-declined. Contract tests passed because fixtures are from March." },
  { key: 'PAY-1836', type: 'task', status: 'not_started', assignee: 'titus.nakamura@ferry.example', title: 'Nightly re-record of PSP contract fixtures with schema diff', body: 'Follow-up to PAY-1834. Re-record against each provider sandbox nightly and fail the build on any schema diff. Also alert on unknown enum values seen in production traffic.' },
  { key: 'PAY-1829', type: 'incident', status: 'done', assignee: 'titus.nakamura@ferry.example', title: 'Webhook redelivery storm - merchant received ~40,000 duplicates', body: "Merchant endpoint 500'd for 14h. Backoff was exponential but uncapped and there was no dead-letter queue. Merchant noticed before we did." },
  { key: 'PAY-1831', type: 'task', status: 'done', assignee: 'titus.nakamura@ferry.example', title: 'Cap webhook attempts at 12 and add a dead-letter queue', body: 'Backoff alone retries forever. Bounded attempts plus DLQ, and a merchant-visible redelivery endpoint.' },
  { key: 'PAY-1855', type: 'bug', status: 'in_progress', assignee: 'victor.almeida@ferry.example', title: 'JPY amounts are 100x too large in merchant statements', body: 'Statement renderer assumes a minor-unit exponent of 2 for every currency. JPY is 0, KWD is 3. Affects every statement for our three Japanese merchants.' },
  { key: 'PAY-1848', type: 'task', status: 'done', assignee: 'victor.almeida@ferry.example', title: 'Reject float amounts at the API boundary', body: 'A merchant posted 10.1 as a float and the ledger balance check failed 400 postings later. Amounts are integers in minor units; the API now rejects anything else with a 422.' },
  { key: 'PAY-1861', type: 'bug', status: 'in_progress', assignee: 'yongyi.tan@ferry.example', title: 'Expired FX quote honoured at capture', body: 'Capture uses the quote attached at authorisation regardless of age. On a 4-minute checkout we are honouring an unhedged rate. Should re-quote past expiry and surface it.' },
  { key: 'PAY-1866', type: 'task', status: 'not_started', assignee: 'titus.nakamura@ferry.example', title: 'Record FX spread as its own ledger posting', body: 'Margin is currently buried inside the converted amount, so FX revenue is invisible in the ledger. Needs a separate posting.' },
  { key: 'PAY-1844', type: 'bug', status: 'done', assignee: 'yongyi.tan@ferry.example', title: 'Reconciliation break auto-adjusted instead of investigated', body: 'A EUR 0.42 break was written off as rounding by the auto-adjust rule. It was actually a duplicated payment of EUR 0.42 net of a fee. Auto-adjust is now disabled for anything but timing breaks.' },
  { key: 'PAY-1857', type: 'story', status: 'in_progress', assignee: 'nushka.petrova@ferry.example', title: 'Classify reconciliation breaks by type', body: 'Timing, amount mismatch, missing, duplicate. Only timing may auto-resolve on the next file. Everything else queues for a human.' },
  { key: 'PAY-1852b', type: 'bug', status: 'done', assignee: 'yongyi.tan@ferry.example', title: 'Partial payout batch failure paid 40 merchants twice on retry', body: 'Batch of 60 failed at merchant 41. Retry re-ran the whole batch. Idempotency must be per-merchant, not per-batch - the batch is not the unit of atomicity.' },
  { key: 'PAY-1869', type: 'task', status: 'not_started', assignee: 'shane.delaney@ferry.example', title: 'Show netting on merchant payout statements', body: 'Every short payout generates a support ticket because refunds, chargebacks and fees are netted invisibly. Statement must itemise the netting.' },
  { key: 'PAY-1826', type: 'bug', status: 'done', assignee: 'julian.reyes@ferry.example', title: 'Authorisation held 8 days then capture failed', body: "Issuer auth holds expire around 7 days. Our record still said 'authorised' so the merchant dashboard promised money that could not be captured. Need expiry tracked in the state machine." },
  { key: 'PAY-1838', type: 'task', status: 'done', assignee: 'nushka.petrova@ferry.example', title: 'Reject settled -> authorised transition', body: 'A replay tool could push a settled payment back to authorised. Nothing validated the transition. State machine now rejects it explicitly with a test per illegal edge.' },
  { key: 'PAY-1872', type: 'task', status: 'not_started', assignee: 'nushka.petrova@ferry.example', title: 'Retry only soft declines', body: 'We currently retry every non-2xx, including hard declines like stolen card. At best useless, at worst it looks like card testing to the acquirer.' },
  { key: 'PAY-1875', type: 'story', status: 'not_started', assignee: 'quinn.halloran@ferry.example', title: 'Dry-run harness for ledger migrations against a prod snapshot', body: 'Follow-up to PAY-1863. Staging row counts are 4% of production, so staging timings are meaningless for lock duration. Needs a restored snapshot and a timing report in CI.' },
  { key: 'PAY-1877', type: 'task', status: 'not_started', assignee: 'titus.nakamura@ferry.example', title: 'Balance check job: derived balances vs replayed postings', body: 'The balances table is a cache but nothing asserts it matches a replay of postings. Nightly job should fail loudly on divergence.' },
  { key: 'PAY-1880', type: 'story', status: 'not_started', assignee: 'shane.delaney@ferry.example', title: 'Merchant-facing SCA exemption reporting', body: 'Merchants need to see their exemption rate and challenge rate before 1 October so they can predict the conversion hit. Blocked on PAY-1870.' },
  { key: 'PAY-1881', type: 'story', status: 'in_progress', assignee: 'meilin.chua@ferry.example', title: 'Checkout: skip the challenge for returning low-value payments', body: '22% of customers drop at the 3DS challenge screen. Proposal is to skip it for returning customers under EUR 30. Blocked on a written answer to which parts of the flow are mandated by the scheme and which are ours: skipping a challenge is only legal if we claim an exemption for that payment, and the low-value band changes on 1 October.' },
  { key: 'PAY-1882', type: 'task', status: 'not_started', assignee: 'meilin.chua@ferry.example', title: "Move the 'checking with your bank' state out of its own screen", body: 'The interstitial is a full page for a state that usually lasts under two seconds, and it renders for authorised payments too because the front end reads the state machine wrong. Needs the real set of states before it can be redesigned.' },
]

interface DocSection {
  anchor: string
  heading: string
  body: string
}

// Excerpted from learning_service/fixtures/ferry/sprint-history.md, one
// entry per `##` heading — anchors are the GitHub-style heading slugs
// `grounded_in` entries already use (lowercased, punctuation stripped,
// spaces to hyphens).
const SPRINT_HISTORY_SECTIONS: DocSection[] = [
  {
    anchor: 'sprint-42--stop-double-charging-current-112-september',
    heading: 'Sprint 42 — "stop double-charging" (current, 1–12 September)',
    body: "Nine duplicate-charge reports in August, all traced to the retry policy in orchestrator. The sprint goal is that a retry can never become a second charge.\n\nDone — PAY-1841: audit of every retry path; found three that mint a fresh idempotency key\nDone — PAY-1847: retry attempts now share the original key\nIn progress — PAY-1852: bound total attempts and surface retry state to the customer\nIn progress — PAY-1859: idempotency key TTL raised to 72h so it exceeds the retry window\nBlocked — PAY-1863: ledger migration add_posting_currency (reverted Tuesday)\nNot started — PAY-1870: SCA exemption changes for 1 October",
  },
  {
    anchor: 'the-reverted-migration-tuesday-8-september',
    heading: 'The reverted migration (Tuesday 8 September)',
    body: 'add_posting_currency added a currency column to postings and backfilled it in a single UPDATE. In staging that held a lock on postings for 34 seconds. postings is on the write path of every payment, so in production it would have stalled the entire platform.\n\nReverted the same afternoon. Before it goes back in:\n1. Chunked batches of 10,000 rows with a pause between them\n2. Run off-peak (after 02:00 UTC)\n3. A dry run against a production-sized snapshot — staging has 4% of the rows, which is exactly why the original timing looked fine\n\nThis is the 0:55 team-quiz question. Four of ten can explain the lock; one can explain why the dry run matters.',
  },
  {
    anchor: 'the-adyen-field-change-august',
    heading: 'The Adyen field change (August)',
    body: 'Adyen began returning refusalReasonCode where the connector expected refusalReason. The adapter fell through to "unknown decline" for nine days. 1,400 payments were retried that should have been hard-declined.\n\nContract tests passed throughout, because they run against fixtures recorded in March. Daniel\'s post-mortem line: "a fixture you never re-record is a test that you have not changed your mind."',
  },
  {
    anchor: 'the-webhook-redelivery-storm-28-august',
    heading: 'The webhook redelivery storm (28 August)',
    body: "A merchant's endpoint began returning 500. The gateway retried with exponential backoff but no attempt cap and no dead-letter queue. Over 14 hours the merchant received roughly 40,000 duplicate events. They noticed before we did.",
  },
  {
    anchor: 'coming-sca-changes-1-october',
    heading: 'Coming: SCA changes, 1 October',
    body: 'The PSD2 low-value exemption threshold drops, and transaction-risk-analysis exemptions require stronger evidence. More transactions will be challenged and conversion will fall. Shane is drafting merchant comms. Nobody on the engineering side can currently explain which exemptions Ferry claims — which is what the team view is supposed to reveal.',
  },
]

const ISSUE_BY_KEY = new Map(ISSUES.map((i) => [i.key, i]))
const SECTION_BY_ANCHOR = new Map(SPRINT_HISTORY_SECTIONS.map((s) => [s.anchor, s]))
const VENDORED_1_CONTEXT_FILES = new Set(['sprint-history.md'])

export type Citation =
  | ({ kind: 'issue'; ref: string } & IssueRecord)
  | ({ kind: 'doc'; ref: string; file: string } & DocSection)
  | { kind: 'unavailable'; ref: string; file?: string }

/** Resolves one `topic.grounded_in` entry — a bare issue key (`PAY-1847`) or
 * a `file#anchor` reference — to its excerpt from the vendored `1-context/`
 * files. Never throws: an unresolvable ref (unknown key, or a file this repo
 * never vendored) comes back as `kind: 'unavailable'` so the view can say so
 * instead of rendering nothing. */
export function resolveCitation(ref: string): Citation {
  const issue = ISSUE_BY_KEY.get(ref)
  if (issue) return { kind: 'issue', ref, ...issue }

  const hashIndex = ref.indexOf('#')
  if (hashIndex === -1) return { kind: 'unavailable', ref }

  const file = ref.slice(0, hashIndex)
  const anchor = ref.slice(hashIndex + 1)
  const section = VENDORED_1_CONTEXT_FILES.has(file) ? SECTION_BY_ANCHOR.get(anchor) : undefined
  if (section) return { kind: 'doc', ref, file, ...section }

  return { kind: 'unavailable', ref, file }
}
