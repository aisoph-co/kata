"""CI1 (`build-day/issues.md` "CI1", KATA-13): the extraction layer behind
`GET /admin/ingest`.

`ingestion.py` owns the trigger + SSE streaming plumbing and the
citation-accurate concept discovery (`extract_concept_drafts`/
`extract_related_pairs`, one concept per distinct `concepts` slug tagged on
a seeded issue). This package is what turns a co-occurring concept pair and
a concept draft into a real curriculum:

- `sources.py` — the second and third grounding sources (release notes, and
  the closest thing this seed has to a repo source: real code identifiers
  named in those release notes), plus folding them into a concept's
  citations.
- `client.py` / `stub.py` — the `ExtractionClient` that classifies a
  co-occurring concept pair as `prerequisite` vs `related` and drafts one
  citation-grounded multiple-choice item per concept, real (OpenRouter) or
  deterministic (stub, for tests/demos, behind `LEARNING_LLM=stub`).
- `exa.py` — the fourth source: a best-effort external citation for a
  concept whose local sources leave it thin.
"""

from __future__ import annotations
