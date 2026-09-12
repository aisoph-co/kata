# Repo excerpts

Real-shaped code from the Ferry monorepo. Every excerpt below **contains the bug
or the fix** that a concept is about, so ingestion (sub-project 4) has something
to ground an item in rather than paraphrasing the concept description.

```
ferry/
├── services/
│   ├── checkout-api/        TypeScript
│   ├── orchestrator/        Go   ← retries, idempotency, state machine
│   ├── psp-connectors/      Go   ← adapters + contract tests
│   ├── ledger/              Go   ← double-entry postings
│   ├── fx-service/          Python
│   ├── settlement/          Python
│   └── webhook-gateway/     Go
└── migrations/
```

## `orchestrator/retry.go` — before PAY-1847

The bug behind nine duplicate charges. A fresh key per attempt means the
acquirer cannot collapse the retries.

```go
func (o *Orchestrator) retryPayment(ctx context.Context, p *Payment) error {
	for attempt := 1; attempt <= 3; attempt++ {
		// BUG: a new key per attempt. The acquirer sees three distinct charges.
		key := uuid.NewString()
		res, err := o.acquirer.Charge(ctx, p.Amount, p.Card, key)
		if err == nil {
			return o.transition(p, Captured)
		}
		time.Sleep(backoff(attempt))
	}
	return ErrRetriesExhausted
}
```

## `orchestrator/retry.go` — after PAY-1847

```go
func (o *Orchestrator) retryPayment(ctx context.Context, p *Payment) error {
	// The key belongs to the intent, not the attempt. Every retry of this
	// payment carries it, so the acquirer collapses them into one charge.
	key := p.IdempotencyKey

	for attempt := 1; attempt <= maxAttempts; attempt++ {
		if !isRetryable(p.LastDecline) {
			return ErrHardDecline // PAY-1872: never retry a stolen card
		}
		res, err := o.acquirer.Charge(ctx, p.Amount, p.Card, key)
		if err == nil {
			return o.transition(p, Captured)
		}
		o.notifyCustomerRetrying(p, attempt) // PAY-1852: they must not be in the dark
		time.Sleep(backoff(attempt))
	}
	return ErrRetriesExhausted
}
```

## `orchestrator/idempotency.go` — the TTL that PAY-1859 is about

```go
const (
	keyTTL          = 24 * time.Hour
	maxRetryWindow  = 26 * time.Hour // ← exceeds keyTTL. This is the bug.
)

// Once the record expires the key means nothing and a late retry looks like a
// brand new charge. The invariant we need is keyTTL > maxRetryWindow, asserted
// in a test rather than maintained by memory.
func (s *Store) Claim(ctx context.Context, key string) (*Record, bool, error) {
	// The race is resolved by the unique constraint, not by check-then-insert:
	// a read followed by a write has a window, and two nodes will both take it.
	rec, err := s.insertOrGet(ctx, key, keyTTL)
	...
}
```

## `ledger/posting.go` — why postings are immutable

```go
// Postings are append-only. A wrong posting is corrected by writing its
// reversal and then the correct entry, never by mutation: the history of what
// we believed, and when, is the thing a regulator asks for.
func (l *Ledger) Correct(ctx context.Context, wrong PostingID, right Posting) error {
	if err := l.write(ctx, reversalOf(wrong)); err != nil {
		return err
	}
	return l.write(ctx, right)
}

// Every movement is at least two postings summing to zero.
func (l *Ledger) write(ctx context.Context, p Posting) error {
	if sum(p.Entries) != 0 {
		return fmt.Errorf("unbalanced posting: entries sum to %d", sum(p.Entries))
	}
	...
}
```

## `migrations/0142_add_posting_currency.sql` — reverted 8 September

```sql
-- REVERTED. Held a lock on postings for 34s in staging, which has 4% of
-- production rows. In production this stalls every payment write path.
ALTER TABLE postings ADD COLUMN currency CHAR(3);
UPDATE postings SET currency = (SELECT currency FROM accounts WHERE ...);
ALTER TABLE postings ALTER COLUMN currency SET NOT NULL;
```

The shape it has to take instead (PAY-1875): add nullable, backfill in chunks of
10,000 with a pause, add a `NOT VALID` check constraint, validate it separately,
then set `NOT NULL`. Run off-peak, after a dry run against a restored snapshot.

## `money/money.go` — the JPY bug in PAY-1855

```go
// BUG: not every currency has two decimal places. JPY is 0, KWD is 3.
func FormatMinor(amountMinor int64, currency string) string {
	return fmt.Sprintf("%.2f", float64(amountMinor)/100)
}

// Correct: the exponent is a property of the currency, and the conversion
// never passes through a float.
func FormatMinor(amountMinor int64, currency string) string {
	exp := MinorUnitExponent(currency) // JPY 0, EUR 2, KWD 3
	return decimal.NewFromInt(amountMinor).Shift(-int32(exp)).StringFixed(int32(exp))
}
```

## `psp-connectors/adyen/decline.go` — the nine-day silent failure

```go
func mapDecline(resp AdyenResponse) DeclineReason {
	switch resp.RefusalReason { // Adyen now sends RefusalReasonCode
	case "Refused":            return SoftDecline
	case "Stolen Card":        return HardDecline
	default:
		// Falls through silently. For nine days every Adyen decline landed
		// here and was retried, including the ones that must never be.
		return UnknownDecline
	}
}
```

`psp-connectors/adyen/testdata/decline_responses.json` is dated `2026-03-14`.
Nobody re-recorded it. The contract test passed every day of the outage.

## `webhook-gateway/deliver.go` — before PAY-1831

```go
// Exponential backoff with no cap and no dead-letter destination. When a
// merchant endpoint 500s for 14 hours this is a 40,000-event flood, not a retry.
for {
	if err := post(ctx, endpoint, event); err == nil {
		return nil
	}
	time.Sleep(backoff(attempt))
	attempt++
}
```
