## hermes-kata

The single Hermes plugin that is the entire integration surface between
Hermes and the Kata learning service — no other file in the Hermes config
talks to the learning service.

Spec: `docs/superpowers/specs/2026-09-06-hermes-surface-spec.md` in
`aisoph-co/agents-everywhere-hackathon` (§1–2 for tool catalog + identity,
§5/§7 for toolset lockdown, §8 for MCQ/MSQ rendering).

- `hermes_kata/catalog.py` — loads the frozen tool catalog (vendored at
  `hermes_kata/tools.json`, or `$KATA_TOOLS_JSON` if set) and registers one
  Hermes tool per entry.
- `hermes_kata/identity.py` — the `pre_gateway_dispatch` hook: resolves the
  inbound message's identity before the agent turn starts, refuses unknown
  identities with a fixed string, never auto-creates.
- `hermes_kata/forwarder.py` — one handler per endpoint, forwarding tool
  calls with the bound identity and the service token.
- `hermes_kata/client.py` — the learning-service HTTP client.
- `hermes_kata/prompts.py` — the system-prompt instruction that routes
  `mcq`/`msq` items through the built-in `clarify` tool instead of chat text.
- `hermes_kata/guardrails.py` — the Socratic guardrail constants (bypass
  phrases, concession phrases, the 8-word overlap threshold) and the
  system-prompt rules that state them; `tests/test_guardrails.py` runs the
  five guardrail assertions against a seeded transcript until KAT-X3's
  real eval set (AGCTM-16) lands.
- `hermes_kata/digests.py` — issue G1: plans and (idempotently, by `name`)
  creates the digest cron jobs — one due-rep job per person with a
  resolvable chat id, one team-quiz job (the only kind that also carries
  `clarify`), one teach-back job.
- `hermes_kata/quiz.py` — issue G1: plans the daily team-quiz post
  (confidence picker, then each item, both via `clarify`; the source chip;
  the live "N of 9 answered" line) and tracks which item ids are today's
  round, so a resolved answer to one of them is written `source =
  slack_thread` (`forwarder.py`'s `is_quiz_item` hook).
- `hermes_kata/reveal.py` — issue G1 (AGCTM-69): tallies resolved answers
  per (item, option) — counts only, never who picked what — credits a
  correct answerer by name, and renders the on-demand reveal.
- `hermes_kata/commands.py` — issue G1's real entry points: registers
  `sync_digest_jobs`, `post_team_quiz`, and `reveal_team_quiz` as ordinary
  Hermes tools (the only extension point `PluginContext` actually offers —
  there is no command-registration hook), plus the system-prompt
  instruction that routes `/kata-sync-digests <channel>` and `/kata-reveal
  <item-id>...` to them, the same "no new rendering code" pattern
  `prompts.py` uses for `mcq`/`msq`.

Toolset lockdown and session pruning are config, not code: see
`deploy/kata/apply-config.sh`.

Run the tests with `pytest plugins/hermes-kata/tests`.
