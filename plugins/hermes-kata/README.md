# hermes-kata

The Hermes↔learning-service integration surface (sub-project 2, PRD §9).
Spec: [`docs/superpowers/specs/2026-09-06-hermes-surface-spec.md`](../../docs/superpowers/specs/2026-09-06-hermes-surface-spec.md).
Framework-agnostic contract this implements: [`docs/adapter-contract.md`](../../docs/adapter-contract.md).

No other file in the Hermes config talks to the learning service.

This build ships the plugin's skeleton, its two config-only companions, and
the digest/team-quiz cron jobs:

| Module | Job (adapter-contract) | Spec section |
|---|---|---|
| `hermes_kata/identity.py` | 1. Bind identity | §2 |
| `hermes_kata/tools.py` | 2. Forward tools | §1 |
| `hermes_kata/mcq.py` | 3. Render choice items | §8 |
| `hermes_kata/digest.py` | 4. Digest cron jobs (due-rep, team-quiz, teach-back) | §6 |
| `hermes_kata/quiz.py` | 4. Team quiz: post, collect, reveal (frames 06-07) | §6, §8 |

Toolset lockdown + session pruning (spec §5) is config, not plugin code —
see `deploy/kata/hermes/apply-config.sh`. Context injection (§3) and the Socratic
guardrails (§4) are tracked as separate issues and are not in this plugin
yet.

### Digest cron jobs (spec §6)

`digest.py` creates one `cron.jobs.create_job` per digest kind per
recipient — a due-rep job per roster person, one team-quiz job, one
teach-back job — each scoped to the `learning` toolset only, and each with
its acting identity recorded in `tools.py`'s `JobIdentityRegistry` so a
cron-triggered turn (no session to bind identity from) can still resolve
one.

`register()` wires this in as a best-effort, config-driven step: linking
(below) and job creation are both no-ops unless `KATA_DIGEST_ROSTER` is set;
job creation additionally needs `ctx.cron` and a team recipient —

- `KATA_DIGEST_ROSTER` — path to a JSON file `[{"person_id", "platform",
  "external_id"}, ...]`, written by a deploy step after `POST
  /admin/roster/import` completes (this plugin has no roster-listing
  endpoint to read from itself; the frozen `tools.json` doesn't have one).
- `KATA_TEAM_RECIPIENT_PLATFORM` / `KATA_TEAM_RECIPIENT_EXTERNAL_ID` — the
  chat the team-quiz and teach-back jobs post into.

Neither variable is set by anything in this repo yet — a maintainer wires
the roster-file-writing deploy step once `POST /admin/roster/import`'s
response shape (KATA-4) is available to script against.

### Team quiz (spec §6, §8, frames 06-07)

`quiz.py` posts the daily question (drawn from a sprint artifact, e.g. the
`PAY-1863` reverted-migration thread) as `clarify` Block Kit buttons with a
confidence gate (1-5) and an "N of M answered" line, grades a tap through
the same `submit_review` forwarder `tools.py` already registers, and
reveals only on `handle_reveal_command` (wire this into Hermes's own
`/kata-reveal` slash-command dispatch, AGCTM-69) — never a timer, never a
name next to an answer or an individual's wrong answer, always the team
leaderboard.

`handle_reveal_command` returns the reveal already shaped as the Slack
Block Kit template in `docs/demo/slack/kata-reveal.blockkit.json`
(`render_reveal_blocks`) — `{"blocks": [...]}`, postable as-is: a
question section with a `` `correct of audience` `` header chip (⚠️ below
a 20% correct rate) and a text-bar line per option (✅ + bold marks
`DailyQuestion.correct_index`), a divider, an optional team-note
blockquote, the leaderboard, and a `context` block naming what Kata
recorded, matching that template's own mock → Block Kit mapping.

Every quiz-answer grading call asserts `quiz_answer_identity(external_id)`,
never the learner's own platform — the core's `_SOURCE_BY_PLATFORM`
(`agency-v1/learning_service/reviews.py`) maps `"slack"` unconditionally to
`"slack_dm"`, so `review.source = slack_thread` can only come from a
platform value that isn't one of that table's keys (`test_quiz_review_
source.py` asserts this against the real mapping, not a copy of it).

That alone would 403 `unknown_identity` against a real roster-imported DB —
`resolve_identity` still needs a matching `Identity` row, and roster import
only ever creates one with `platform="slack"`. `register()` closes that gap
for every learner in `KATA_DIGEST_ROSTER` via `ensure_quiz_thread_identity`:
mint a link code on the learner's existing `slack` identity
(`POST /me/link-code`) and consume it under `platform="slack_thread"`
(`POST /identities/link`) — both already in the frozen `tools.json`, so
this is config/data, not a contract change. Idempotent by tolerance: a
second run's `IdentityAlreadyLinked` (fixed message, asserted against the
real source in `test_quiz_thread_identity_link.py`) is treated as success.

## Running the tests

Run from this repo's root, with `agency-v1` checked out as a sibling
directory (`tools.json`'s source — `hermes_kata/tools.py`'s default catalog
path resolution):

```sh
pip install -e "./plugins/hermes-kata[dev]"
pytest plugins/hermes-kata/tests
```

No live Hermes process or database is needed — every test is either a pure
function or a fake standing in for the documented `PluginContext`/hook API
(`tests/fakes.py`).

Not yet wired into a GitHub Actions workflow — the push credential used to
build this PR didn't have the `workflow` scope needed to add one. A
maintainer should add a job mirroring `web`'s shape in `.github/workflows/
ci.yml`, checking out `aisoph-co/agency-v1` as a sibling path and running the
commands above.

## Installing into the Kata Hermes instance

`deploy/kata/hermes/Dockerfile` bakes this directory into the `hermes-v3`
image at `/opt/kata/plugins/hermes-kata`, and its `sync-kata-plugin.sh`
cont-init hook copies it onto the volume at boot, at
`$HERMES_HOME/plugins/hermes-kata/` — Hermes's real "user" plugin discovery
sweep (`hermes_cli/plugins_discovery.py::collect_directory_manifests`) scans
exactly `get_hermes_home() / "plugins"`, confirmed against a live `hermes-v3`
(KATA-17 deploy verification). `$HERMES_HOME/.hermes/plugins/` — this
section's own claim before that verification — is never scanned at all; a
copy placed there is invisible to `hermes plugins list`/`enable`/`doctor`
and never registers a single tool or hook. `apply-config.sh` sets
`plugins.enabled: ["hermes-kata"]` (Hermes plugins are opt-in by default) —
also run automatically at boot, as of KATA-17.

For a manual/non-Railway install: copy `plugins/hermes-kata/` onto the
`hermes` service's `$HERMES_HOME/plugins/hermes-kata/`, run `hermes plugins
enable hermes-kata`, then restart the gateway so it picks up the new plugin
on the next boot.

`LEARNING_SERVICE_URL`/`LEARNING_SERVICE_TOKEN` must already be set in the
Hermes environment (`deploy/kata/env.hermes.example`) — if they aren't yet in
a given environment, every message 403s at the gateway; that's expected, not
a plugin bug.

`KATA_TOOLS_JSON`, if set, points straight at a `tools.json` file and always
wins. Unset, the default falls back to `LEARNING_SERVICE_SRC` (default a
sibling `agency-v1/` checkout — `tools.json` lives there with the learning
service) plus `learning_service/tools.json`.
