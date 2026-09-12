# Sprint history

What Kata ingests at the 0:10 beat, and the source of the team-quiz questions.

## Sprint 42 — "stop double-charging" (current, 1–12 September)

Nine duplicate-charge reports in August, all traced to the retry policy in
`orchestrator`. The sprint goal is that a retry can never become a second charge.

| Status | Work |
|---|---|
| Done | `PAY-1841` — audit of every retry path; found three that mint a fresh idempotency key |
| Done | `PAY-1847` — retry attempts now share the original key |
| In progress | `PAY-1852` — bound total attempts and surface retry state to the customer |
| In progress | `PAY-1859` — idempotency key TTL raised to 72h so it exceeds the retry window |
| Blocked | `PAY-1863` — ledger migration `add_posting_currency` (reverted Tuesday) |
| Not started | `PAY-1870` — SCA exemption changes for 1 October |

## The reverted migration (Tuesday 8 September)

`add_posting_currency` added a `currency` column to `postings` and backfilled it
in a single `UPDATE`. In staging that held a lock on `postings` for **34 seconds**.
`postings` is on the write path of every payment, so in production it would have
stalled the entire platform.

Reverted the same afternoon. Before it goes back in:

1. Chunked batches of 10,000 rows with a pause between them
2. Run off-peak (after 02:00 UTC)
3. A dry run against a production-sized snapshot — staging has 4% of the rows,
   which is exactly why the original timing looked fine

*This is the 0:55 team-quiz question. Four of ten can explain the lock; one can
explain why the dry run matters.*

## The Adyen field change (August)

Adyen began returning `refusalReasonCode` where the connector expected
`refusalReason`. The adapter fell through to "unknown decline" for nine days.
1,400 payments were retried that should have been hard-declined.

Contract tests passed throughout, because they run against fixtures recorded in
March. Daniel's post-mortem line: *"a fixture you never re-record is a test that you
have not changed your mind."*

## The webhook redelivery storm (28 August)

A merchant's endpoint began returning 500. The gateway retried with exponential
backoff but no attempt cap and no dead-letter queue. Over 14 hours the merchant
received roughly **40,000 duplicate events**. They noticed before we did.

## Coming: SCA changes, 1 October

The PSD2 low-value exemption threshold drops, and transaction-risk-analysis
exemptions require stronger evidence. More transactions will be challenged and
conversion will fall. Shane is drafting merchant comms. Nobody on the
engineering side can currently explain which exemptions Ferry claims — which is
what the team view is supposed to reveal.
