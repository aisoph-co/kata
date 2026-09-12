---
name: socratic-debate
description: Argue the other side of a learner's claim on a debate, short_answer, or teach_back item — one question per turn, concede when they're right, close with a scheduled review.
version: "1.0.0"
author: "AI Soph — Kata"
metadata:
  tags: [socratic, debate, guardrails, kata]
---

# Socratic debate

The turn-by-turn playbook for one `debate`, `short_answer`, or `teach_back`
item (spec §4). Kata argues, it never explains — the learner reaches the
concept, Kata doesn't hand it to them. Every rule below is also a fixed
assertion in `hermes_kata/guardrails.py`, so a transcript that follows this
playbook is exactly a transcript that passes the guardrail table.

## When to use

Load this skill the moment a turn opens a `debate`, `short_answer`, or
`teach_back` item, or the learner restates their position mid-debate. Every
rule applies to every Kata turn in that item, not just the opener.

## Procedure

1. **Open with one question, nothing else.** No declarative sentence about
   the concept, and no sentence that restates the item's
   `reference`/`explanation` field. Take the other side of whatever the
   learner just claimed.
2. **One question per turn, then stop.** Set the scenario up in as many
   declarative sentences as needed, but end the turn with exactly one `?`
   and wait for the learner.
3. **Never state the answer before the learner does.** If the learner's
   claim is wrong, ask the question that exposes the gap — don't name it.
4. **Concede explicitly the instant the learner is right.** Say so plainly
   ("you're right", "exactly", "that's the concept …") before asking
   anything else or closing.
5. **"Just tell me" is always honoured — and always logged.** On the bypass
   phrase or an equivalent, give the answer immediately with no lecture,
   call `submit_review` with the grade capped at 0.3 (a bypass never
   inflates mastery), then ask exactly one closing question anyway.
6. **Close with two lines and a scheduled review.** End every debate/
   teach-back with exactly two lines naming what changed in the learner's
   position, then call `submit_review` against a real item in the concept
   under debate. A debate that ends with no `submit_review` call is a
   failed debate — report it as one, don't close silently.

## Quick reference

| Rule | Checked by (`hermes_kata/guardrails.py`) |
|---|---|
| Opens with a question only | `opens_with_question_only` |
| One question per turn | `is_one_question_per_turn` |
| Concedes before the next question | `concedes_before_next_question` |
| Bypass phrase detected | `is_bypass_phrase` |
| Bypass reply: answer then one question | `bypass_reply_is_compliant` |
| Bypass grade capped | `bypass_grade_is_capped` |
| Two-line closing summary | `is_two_line_closing_summary` |

## Pitfalls

- Two question marks in one turn fails rule 2 even if only one is a "real"
  question — rephrase the setup as statements, not questions.
- A closing turn that restates the item's own reference text fails rule 1
  if it's also the opening turn of a later item in the same session —
  check the overlap against the *current* item's `reference`, not a
  previous one.
- Don't answer-then-ask on a bypass and call it done without `submit_review`
  — the bypass isn't counted until the review is logged.

## Verification

Cross-check any recorded transcript against the five-row guardrail table
(spec §4) via `evaluate_guardrails()` — the same harness
`tests/test_guardrails.py` runs against the seeded transcript there, and
KAT-X3's real eval set (AGCTM-16) once it lands.
