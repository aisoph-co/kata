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

Toolset lockdown and session pruning are config, not code: see
`deploy/kata/apply-config.sh`.

Run the tests with `pytest plugins/hermes-kata/tests`.
