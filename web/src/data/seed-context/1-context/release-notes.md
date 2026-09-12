# Ferry release notes (last four weeks)

Ingestion source for "what changed recently"; the team quiz draws sprint
questions from here.

## 2026-09-04 · `orchestrator` v2.14.0
- Retry attempts now share the payment intent's idempotency key (`PAY-1847`).
  Fixes the duplicate-charge cluster reported through August.
- **Known gap:** attempts are still uncapped and the customer sees nothing
  while a retry is in flight (`PAY-1852`).

## 2026-09-02 · `ledger` v1.9.3
- Auto-adjustment of reconciliation breaks restricted to timing breaks only
  (`PAY-1844`). A EUR 0.42 "rounding" write-off turned out to be a duplicated
  payment.

## 2026-08-29 · `webhook-gateway` v3.2.0
- Delivery attempts capped at 12, with a dead-letter queue and a
  merchant-visible redelivery endpoint (`PAY-1831`).
- Post-incident for the 28 August redelivery storm.

## 2026-08-27 · `psp-connectors` v4.7.1
- Handle Adyen's `refusalReasonCode` (`PAY-1834`). Nine days of declines were
  mapped to `UnknownDecline` and retried; 1,400 of those should have been hard
  declines.
- Contract fixtures still dated 2026-03-14. Re-recording is `PAY-1836`.

## 2026-08-22 · `checkout-api` v5.1.0
- Reject non-integer amounts at the API boundary with 422 (`PAY-1848`).

## 2026-08-19 · `orchestrator` v2.13.2
- Track issuer authorisation expiry in the payment state machine (`PAY-1826`).
  An 8-day-old hold is no longer reported as capturable.
- Reject the `settled → authorised` transition (`PAY-1838`).

## Reverted

## 2026-09-08 · `ledger` migration 0142 — **reverted the same day**
- `add_posting_currency` locked `postings` for 34 seconds during backfill in
  staging. Reverted before it reached production (`PAY-1863`).
