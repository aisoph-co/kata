# Ferry — the seeded team's product

> Seed data for Kata's golden scenario. Ferry is fictional. Nothing here is
> confidential and nothing is copied from a real employer; the roster *shape*
> mirrors ours (§12 of the board), the content does not.
>
> Rename in one pass if "Ferry" doesn't survive: `rg -l Ferry | xargs sed -i '' 's/Ferry/<name>/g'`.

## What Ferry sells

Ferry is a **cross-border payments platform for small merchants**. A boutique in
Lisbon sells to a customer in Berlin; Ferry takes the card payment in euros,
handles the regulator's authentication rules, converts to the merchant's payout
currency, and settles to their bank two days later.

Three things the merchant buys:

1. **Accept** — card payments from customers in 30 countries, one integration.
2. **Convert** — a locked FX rate at checkout, so the merchant knows what they'll receive.
3. **Settle** — one payout per currency per day, reconciled, with a statement that matches the bank.

Ferry is ~40 people. The team we seed is the **Payments Core** team of ten: they
own everything between "customer taps card" and "money lands in the merchant's
account". They do not own the merchant dashboard, onboarding/KYC, or the mobile SDKs.

## Why this domain

It gives each persona genuinely different material — which is the whole claim
behind *"beats a generic AI tutor"* (board §3). The PM's topics are regulatory,
the juniors' are correctness-under-retry, the seniors' are data integrity and
integration contracts. Nobody's rep list looks like anybody else's.

It also has unambiguous right answers, which matters when an agent generates the
items and a judge from a bank is watching.

## Architecture the team owns

```
                    ┌───────────────┐
   customer  ──────▶│  checkout-api │  quote, authorise, 3DS
                    └───────┬───────┘
                            │
                    ┌───────▼───────┐
                    │  orchestrator │  state machine, retries, idempotency
                    └───┬───────┬───┘
                        │       │
          ┌─────────────▼─┐   ┌─▼──────────────┐
          │ psp-connectors │   │    ledger      │  double-entry, immutable
          │ (Stripe, Adyen,│   └─┬──────────────┘
          │  Rapyd, local) │     │
          └────────────────┘     │
                    ┌────────────▼──────┐
                    │  fx-service       │  quotes, spread, expiry
                    └────────────┬──────┘
                                 │
              ┌──────────────────▼─────────┐
              │ settlement + reconciliation │  T+2 payouts, break detection
              └──────────────┬──────────────┘
                             │
                    ┌────────▼────────┐
                    │  webhook-gateway │  at-least-once to merchants
                    └──────────────────┘
```

| Service | Language | Owns | Primary owner |
|---|---|---|---|
| `checkout-api` | TypeScript | Quote presentation, 3DS challenge flow | Victor, Nushka, **Mei Lin** (design) |
| `orchestrator` | Go | Payment state machine, retry policy, idempotency store | Hugo, Julian, **Daniel** |
| `psp-connectors` | Go | One adapter per acquirer; contract tests against recorded fixtures | **Daniel**, Titus |
| `ledger` | Go + Postgres | Double-entry journal, immutable postings, balances | **Yong Yi**, Nushka |
| `fx-service` | Python | Rate sourcing, spread, quote expiry | **Yong Yi**, Titus |
| `settlement` | Python | Payout batching, cutoffs, reconciliation against bank files | **Yong Yi**, Nushka |
| `webhook-gateway` | Go | Merchant event delivery, retries, dedupe | Titus, Julian |

## The live situation (what the team is working on right now)

This is what Kata ingests at the 0:10 demo beat, and what the team quiz draws on.

- **Sprint 42 is in flight.** The theme is *"stop double-charging"* — a cluster of
  duplicate-charge reports traced back to the retry policy in `orchestrator`.
- **The ledger migration was reverted on Tuesday.** `add_posting_currency` locked
  `postings` for 34 seconds during backfill in staging. It has to go back in
  chunked, off-peak, after a dry run against a production snapshot.
- **PSD2 SCA rules tightened on 1 October.** The low-value exemption threshold
  drops and the transaction-risk-analysis exemption needs new evidence. Shane
  is writing the merchant comms; nobody on the team can yet explain which
  exemptions Ferry actually claims.
- **Adyen changed a response field** without notice in August. The connector
  swallowed it for nine days because the contract tests run against recorded
  fixtures that nobody re-records. Daniel has opinions.
- **The checkout redesign is in review.** Mei Lin has a flow that drops the 3DS
  challenge for returning customers under EUR 30 and moves the "we are checking
  with your bank" state off its own screen. Half of what it changes is Ferry's to
  choose and half is mandated by the scheme; nobody has written down which half is
  which, so the review keeps stalling on the same argument.
- **Webhook redelivery storm** on 28 August: a merchant's endpoint 500'd, the
  gateway retried without a cap, and the merchant received 40,000 duplicate events.
