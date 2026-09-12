# Slack threads

The fifth team-context source in PRD §3 stage 1 — *"repo, docs, issue tracker,
release notes, **a Slack channel**, plus industry sources via Exa"* — and the one
the seed was missing. `issues.jsonl` ends `PAY-1841` with "full list in the
thread"; this is that thread.

Five threads from `#payments-team` and `#payments-incidents`, covering the two
weeks of Sprint 42. Everything here is consistent with `issues.jsonl`,
`sprint-history.md` and `repo-excerpts.md` — the same 34-second lock, the same
1,400 retried payments, the same 40,000 duplicate webhooks.

They earn their place for three reasons. Argument is where a team's real
disagreements live, and a concept map built only from issue titles cannot see
them. Two of the demo's named artifacts are debates rather than tickets — Hugo
on retries, Daniel on contract tests. And `slack_thread` is a `source` value in the
core spec that nothing else in the seed produces.

Handles are the `slack_user_id` values in `0-team/roster.json`. Everyone is
they/them, per `0-team/roster.md`.

---

## 1. `#payments-team` — "why is the retry making a second charge?"

**The thread `PAY-1841` points at.** Hugo arguing themself to idempotency keys,
which is the 0:30 Socratic debate beat in miniature.

> **@hugo** (Mon 09:14)
> Third duplicate-charge report this week and I don't get it. The retry path
> looks fine? We catch the timeout, we back off, we call the acquirer again.
>
> **@daniel** (09:21)
> Call it again *with what key*.
>
> **@hugo** (09:26)
> `uuid4()` at the top of `attemptCharge`. Same as everywhere else.
>
> **@daniel** (09:27)
> There it is.
>
> **@hugo** (09:31)
> Wait — but the whole point of a fresh key is that it's a fresh *attempt*. If I
> reuse the key the acquirer will just hand me back the first response and I've
> lost the retry.
>
> **@daniel** (09:34)
> That is the retry. You're not trying to charge them twice, you're trying to
> find out whether the first charge happened. A timeout doesn't mean it failed,
> it means you don't know. Same key = "tell me about *this* charge". New key =
> "here is a second charge, please take more money".
>
> **@hugo** (09:41)
> …and a timeout is exactly the case where the first one probably did go
> through. So the fresh key guarantees the double charge in the one situation
> the retry exists for. That's horrible.
>
> **@daniel** (09:42)
> Yes.
>
> **@hugo** (09:48)
> Three paths do it. Timeout handler, the acquirer-503 branch, and the manual
> replay endpoint. Replay is the worst one — support hits that button *because*
> they think a payment failed.
>
> **@quinn** (10:02)
> Good. Key comes off the payment intent, not the attempt. `PAY-1847`, Hugo's
> got it. And the TTL on the idempotency record has to be longer than the total
> retry window or a late retry reads as new — @yongyi can you check what it is?
>
> **@yongyi** (10:11)
> 24h. Retry window is capped at… nothing, currently. `PAY-1859`, raising it
> to 72h.
>
> **@julian** (10:30)
> so is the rule just "always reuse the key"
>
> **@daniel** (10:33)
> The rule is the key identifies the *intent*, and every attempt at that intent
> carries it. If you can't say what a key means without saying "attempt", it's
> the wrong key.

---

## 2. `#payments-incidents` — the reverted ledger migration

**Tuesday 8 September.** The 0:55 team-quiz beat: four of nine can explain the
lock, one can explain why the dry run matters.

> **@yongyi** (14:02)
> Rolling back `add_posting_currency`. Staging held a lock on `postings` for
> 34 seconds on the backfill.
>
> **@nushka** (14:04)
> 34s isn't that bad? it's one table
>
> **@yongyi** (14:06)
> `postings` is on the write path of every payment in the company. For 34
> seconds nothing settles, nothing authorises, nothing refunds. In production
> it's not 34 seconds either — staging has about 4% of the rows.
>
> **@titus** (14:09)
> Single-statement `UPDATE` over the whole table?
>
> **@yongyi** (14:09)
> Yep. Holds the lock for its entire duration by definition.
>
> **@victor** (14:15)
> So chunk it. 10k rows at a time with a pause, run it after 02:00.
>
> **@yongyi** (14:17)
> That's two of the three. Chunking bounds how long any single lock is held,
> off-peak bounds what it takes down if we're wrong. Neither of them tells you
> what the timing will actually be.
>
> **@victor** (14:19)
> …because staging is 4% of prod, so the staging number means nothing either
> way.
>
> **@yongyi** (14:21)
> Right. Third thing is a dry run against a restored production snapshot, with
> the timing in CI. Without it we're guessing twice and calling it a plan.
> `PAY-1875`, and it's Quinn's.
>
> **@quinn** (14:40)
> Mine. Nobody re-lands this until that harness exists — the migration wasn't
> the mistake, believing the staging timing was.

---

## 3. `#payments-team` — "the contract tests passed"

**Daniel's thread.** The senior-SWE topic: a suite that cannot fail is not a test.

> **@titus** (11:20)
> Post-mortem q on the Adyen thing — how did nine days of unknown declines get
> past us? The connector has contract tests and they were green the whole time.
>
> **@daniel** (11:26)
> They were green because they've been green since March. The fixtures are from
> March. Adyen renamed `refusalReason` to `refusalReasonCode` in August and our
> recorded responses have never heard of it.
>
> **@titus** (11:28)
> So the tests were passing against a provider that no longer exists.
>
> **@daniel** (11:29)
> Against our memory of one. A fixture you never re-record is a test that you
> have not changed your mind.
>
> **@julian** (11:35)
> couldn't we just hit their sandbox in CI instead
>
> **@daniel** (11:41)
> Then CI fails when their sandbox is down and everyone learns to ignore it.
> The fixture isn't the problem, the fixture *never expiring* is. Record against
> the live sandbox on a schedule, diff it, and make the diff someone's problem
> when it moves.
>
> **@titus** (11:44)
> What did the fallthrough actually cost?
>
> **@daniel** (11:47)
> 1,400 payments retried that should have been hard-declined. Every one of those
> is a customer we annoyed and an issuer we look worse to.
>
> **@yongyi** (11:52)
> Worth saying the type system didn't help us here at all. Missing field
> deserialised to empty string, empty string matched no known code, default
> branch said "unknown decline". Three reasonable decisions, one silent failure.

---

## 4. `#payments-incidents` — the webhook redelivery storm

**28 August.** Where `retry-safety` and `webhook-delivery` stop being separate
concepts.

> **@victor** (08:12)
> A merchant is saying they got "about forty thousand" duplicate events
> overnight. That can't be right, can it
>
> **@yongyi** (08:20)
> It's right. Their endpoint started 500ing around 18:00. We retried with
> exponential backoff, no attempt cap, no dead-letter. Fourteen hours.
>
> **@victor** (08:22)
> Backoff was supposed to stop exactly this though
>
> **@yongyi** (08:25)
> Backoff slows a retry loop down. It doesn't end one. Without a cap and a
> dead-letter queue you've built a very patient denial of service against your
> own customer.
>
> **@hugo** (08:31)
> This is the same shape as the charge retries, isn't it. At-least-once
> delivery, and the fix is that the receiver can dedupe.
>
> **@yongyi** (08:33)
> Same shape, and worth internalising: the sender cannot fix at-least-once. Cap
> the attempts, dead-letter the rest, ship a stable event ID so the receiver can
> throw duplicates away. And *they noticed before we did*, which is its own bug.
>
> **@shane** (09:05)
> For the merchant comms — can I say events may arrive more than once and out of
> order, and they should key off the event ID?
>
> **@yongyi** (09:07)
> Yes, and say it before it happens again rather than after.

---

## 5. `#payments-team` — SCA changes, 1 October

**Shane's thread.** The 1:45 beat: the PM is the only person who can answer this —
including the designer who is mid-way through redrawing the flow the rule governs.

> **@shane** (16:02)
> Low-value exemption threshold drops on 1 Oct and TRA needs stronger evidence.
> More challenges, conversion falls. Drafting merchant comms — before I do, can
> someone tell me which exemptions we actually claim today?
>
> **@shane** (16:31)
> Anyone?
>
> **@daniel** (16:40)
> Genuinely don't know. I thought the issuer decided.
>
> **@shane** (16:44)
> The issuer decides whether to accept it. *We* decide whether to claim one, and
> we carry the fraud liability when we do. That's the trade — better conversion
> now, our loss later if it's challenged and we can't evidence it.
>
> **@quinn** (16:52)
> I'd have guessed low-value and stopped there.
>
> **@shane** (16:55)
> Low-value and transaction risk analysis. TRA is the one that bites: it needs a
> real-time risk score recorded *at authorisation*, plus our fraud rate for the
> band. You cannot produce that afterwards — the whole claim is that the
> assessment informed the decision, and a score computed later evidences nothing
> about what we knew when we skipped the challenge.
>
> **@meilin** (16:58)
> Then can we drop the challenge for returning customers under €30? That screen is
> where the redesign loses people — 22% of them, and most come back and pay on a
> different card, which is worse for us than the challenge was.
>
> **@shane** (17:00)
> You can drop it *if* we claim an exemption for those payments, and after 1 Oct
> the low-value band is smaller than €30. So it isn't a design decision — it's a
> decision about which exemption we claim and whether we can evidence it. Those
> are different arguments and we keep having the first one.
>
> **@nushka** (17:01)
> could we just split a €40 payment into two €20s to stay under the threshold
>
> **@shane** (17:03)
> That's structuring, and it's the exact behaviour the rule exists to stop.
> Please don't ever put that in a PR.
>
> **@meilin** (17:06)
> I've been treating the whole challenge step as ours to change. Which parts of
> that flow are actually mandated? I want it written down before I redraw it
> again — I redrew it twice already on an assumption nobody corrected.
>
> **@quinn** (17:10)
> Shane, can you write this up somewhere that isn't a Slack thread? Three
> engineers just found out we carry that liability, one of them was me, and the
> person redesigning the flow has been guessing at which parts they're allowed to
> touch.
