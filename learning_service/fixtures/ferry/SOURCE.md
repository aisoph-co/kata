# Ferry seed snapshot

Vendored verbatim from the hackathon repo so `learning_service` never
depends on it at runtime. Two issues share this directory for two different
purposes — grounding material for ingestion (CI1, KATA-13) and a demo-seed
scenario (KATA-4) — so the table below is split accordingly.

- Origin: `agents-everywhere-hackathon` @ `origin/main`
- Commit: `081443d983586fbd4d24511ff55c4e61d45ebb1d`
- Source path: `docs/seed/`

## Ingestion grounding source (CI1, `build-day/issues.md` "CI1")

`GET /admin/ingest` walks this material directly; it derives its own
course/concepts/edges/topics from it rather than loading a pre-built
curriculum.

| File here | Source path |
|---|---|
| `issues.jsonl` | `1-context/issues.jsonl` — the primary grounding source `GET /admin/ingest` walks |
| `sprint-history.md` | `1-context/sprint-history.md` — the "release notes" source `extraction.sources.load_release_notes_source` reads |

## Demo-seed scenario (KATA-4, `learning_service.seed`)

`learning_service.fixtures.ferry_scenario.build_ferry_scenario` reshapes
this material into the dict shape `learning_service.seed` writes to
Postgres — a realistic payments-team roster, curriculum and 90-day review
history for `LEARNING_SEED=ferry`.

| File here | Source path |
|---|---|
| `roster.json` | `0-team/roster.json` |
| `concepts.json` | `2-curriculum/concepts.json` |
| `items.json` | `2-curriculum/items.json` |
| `topics.json` | `2-curriculum/topics.json` |
| `reviews.jsonl` | `3-history/reviews.jsonl` |

Re-vendor by re-running `git show origin/main:docs/seed/<path>` against a
newer commit if the upstream seed changes.
