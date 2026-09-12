"""Extraction for `POST /admin/ingest` (KATA-13/CI1).

Two seeds, two jobs, neither invented here:

- `web/src/data/seed-context/1-context/issues.jsonl` is the raw source the
  trigger reads to decide *whether there's anything to ingest at all* (an
  empty file is a real, statable "no issues found" — frame 02's other
  required state) and, from its own per-issue `concepts: [...]` tags, which
  issue key(s) ground each concept.
- `learning_service/seed_data/{concepts,items}.json` (KATA-4's golden-
  scenario loader, `learning_service/seed.py`) is the curated content: real
  titles, descriptions, a human-authored prerequisite/related graph already
  validated acyclic, and real MCQ items — the same file a from-scratch
  `LEARNING_SEED=ferry` boot already writes through this exact curriculum,
  so a re-run against an already-seeded core reuses those rows rather than
  writing a second, divergent copy.

A concept's citations are the issue keys `issues.jsonl` tagged it with —
never fabricated, and independent of whichever items happen to exist for
it. An item inherits its concept's citations; with none, it's written
`draft`, never `published` (the human review gate, KATA-13's own done
check).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

SEED_DATA_DIR = Path(__file__).resolve().parent / "seed_data"


@dataclass(frozen=True)
class ConceptDraft:
    slug: str
    title: str
    description: str
    mastery_threshold: float
    citations: tuple[str, ...]  # sorted issue keys this concept was tagged on in issues.jsonl


@dataclass(frozen=True)
class EdgeDraft:
    from_slug: str
    to_slug: str
    kind: str
    weight: float


@dataclass(frozen=True)
class TopicDraft:
    slug: str
    title: str
    description: str
    persona_role: str
    entry_slug: str
    concept_slugs: tuple[str, ...]
    grounded_in: tuple[str, ...]


@dataclass(frozen=True)
class ItemDraft:
    concept_slug: str
    kind: str
    prompt: str
    payload: dict
    status: str


def default_seed_context_dir() -> Path:
    # This file lives at <repo root>/learning_service/ingestion.py; the seed
    # is vendored at <repo root>/web/src/data/seed-context/1-context (the
    # same files `web/src/lib/seed-citations.ts` reads client-side).
    return Path(__file__).resolve().parents[1] / "web" / "src" / "data" / "seed-context" / "1-context"


def seed_context_dir() -> Path:
    override = os.environ.get("KATA_SEED_CONTEXT_DIR")
    return Path(override) if override else default_seed_context_dir()


def load_issues(seed_dir: Path) -> list[dict]:
    """A missing or empty `issues.jsonl` both return `[]` — "no issues
    found" is a real, statable case (frame 02's empty-source state), not an
    error."""
    path = seed_dir / "issues.jsonl"
    if not path.exists():
        return []
    issues = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        issues.append(json.loads(line))
    return issues


def _load_seed_json(name: str, seed_data_dir: Path) -> object:
    return json.loads((seed_data_dir / name).read_text(encoding="utf-8"))


def load_concepts_doc(seed_data_dir: Path = SEED_DATA_DIR) -> dict:
    return _load_seed_json("concepts.json", seed_data_dir)  # type: ignore[return-value]


def load_items_doc(seed_data_dir: Path = SEED_DATA_DIR) -> list[dict]:
    return _load_seed_json("items.json", seed_data_dir)  # type: ignore[return-value]


def citations_by_slug(issues: list[dict]) -> dict[str, tuple[str, ...]]:
    by_slug: dict[str, set[str]] = {}
    for issue in issues:
        key = issue.get("key")
        for slug in issue.get("concepts", []):
            by_slug.setdefault(slug, set()).add(key)
    return {slug: tuple(sorted(keys)) for slug, keys in by_slug.items()}


def extract_concepts(issues: list[dict], concepts_doc: dict) -> list[ConceptDraft]:
    citations = citations_by_slug(issues)
    return [
        ConceptDraft(
            slug=c["slug"],
            title=c["title"],
            description=c["description"],
            mastery_threshold=c.get("mastery_threshold", 0.85),
            citations=citations.get(c["slug"], ()),
        )
        for c in concepts_doc["concepts"]
    ]


def extract_edges(concepts_doc: dict) -> list[EdgeDraft]:
    edges = [
        EdgeDraft(from_slug=e["from"], to_slug=e["to"], kind="prerequisite", weight=e.get("weight", 1.0))
        for e in concepts_doc.get("prerequisite_edges", [])
    ]
    edges += [
        EdgeDraft(from_slug=e["a"], to_slug=e["b"], kind="related", weight=e.get("weight", 1.0))
        for e in concepts_doc.get("related_edges", [])
    ]
    return edges


def extract_items(items_doc: list[dict], concepts: list[ConceptDraft]) -> list[ItemDraft]:
    """One draft per `items.json` entry, `published` only when its concept
    carries a real citation — `items.json` itself has no citation field of
    its own, so this is the one place that gate is actually enforced."""
    by_slug = {c.slug: c for c in concepts}
    drafts = []
    for it in items_doc:
        concept = by_slug.get(it["concept"])
        citations = concept.citations if concept else ()
        payload = dict(it["payload"])
        if citations:
            payload["grounded_in"] = list(citations)
        drafts.append(
            ItemDraft(
                concept_slug=it["concept"],
                kind=it["kind"],
                prompt=it["prompt"],
                payload=payload,
                status="published" if citations else "draft",
            )
        )
    return drafts


# role -> (slug, title, wanted concept slugs in entry-first order). Grounded
# in `web/src/data/seed-context/1-context/company.md` ("Why this domain"):
# the PM's topics are regulatory/customer-facing, the juniors' is
# correctness-under-retry, the seniors' is data integrity and integration
# contracts; UX design owns the checkout-facing concepts, and the tech lead
# owns settlement correctness end to end. A concept can serve more than one
# persona's topic — there's no exclusivity claim here, just relevance.
_ROLE_TOPICS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "pm",
        "regulatory-and-customer-comms",
        "Regulatory rules and customer-facing status",
        ("sca-exemptions", "payment-status-communication", "challenge-flow-ux"),
    ),
    (
        "uxd",
        "checkout-and-status-ux",
        "Checkout challenge flow and status communication",
        ("challenge-flow-ux", "payment-status-communication"),
    ),
    (
        "junior_swe",
        "correctness-under-retry",
        "Retry safety and idempotent payment state",
        ("idempotency", "retry-safety", "payment-state-machine", "webhook-delivery"),
    ),
    (
        "senior_swe",
        "data-integrity-and-contracts",
        "Data integrity and integration contracts",
        ("double-entry", "ledger-migrations", "money-representation", "psp-contract-testing", "fx-quote-lifecycle"),
    ),
    (
        "tech_lead",
        "settlement-and-reconciliation",
        "End-to-end settlement correctness",
        ("payout-settlement", "reconciliation", "psp-contract-testing"),
    ),
)


def build_topics(concepts: list[ConceptDraft]) -> list[TopicDraft]:
    by_slug = {c.slug: c for c in concepts}
    drafts = []
    for persona_role, slug, title, wanted in _ROLE_TOPICS:
        present = tuple(s for s in wanted if s in by_slug)
        if not present:
            continue
        grounded_in = tuple(sorted({citation for s in present for citation in by_slug[s].citations}))
        if not grounded_in:
            continue
        drafts.append(
            TopicDraft(
                slug=slug,
                title=title,
                description="",
                persona_role=persona_role,
                entry_slug=present[0],
                concept_slugs=present,
                grounded_in=grounded_in,
            )
        )
    return drafts
