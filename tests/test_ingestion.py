"""`learning_service.ingestion` (KATA-13/CI1): pure extraction, tested
without FastAPI or a database — the admin route (`test_admin_ingest.py`)
covers the write side.
"""

from __future__ import annotations

from learning_service.ingestion import (
    ConceptDraft,
    build_topics,
    citations_by_slug,
    extract_concepts,
    extract_edges,
    extract_items,
    load_concepts_doc,
    load_issues,
    load_items_doc,
    seed_context_dir,
)

CONCEPTS_DOC = {
    "course": {"slug": "c", "title": "Course", "description": ""},
    "concepts": [
        {"slug": "idempotency", "title": "Idempotency", "mastery_threshold": 0.85, "description": "d1"},
        {"slug": "retry-safety", "title": "Retry safety", "mastery_threshold": 0.85, "description": "d2"},
        {"slug": "double-entry", "title": "Double entry", "mastery_threshold": 0.9, "description": "d3"},
    ],
    "prerequisite_edges": [{"from": "idempotency", "to": "retry-safety"}],
    "related_edges": [{"a": "retry-safety", "b": "double-entry", "weight": 0.6}],
}

ISSUES = [
    {"key": "PAY-1", "concepts": ["idempotency", "retry-safety"]},
    {"key": "PAY-2", "concepts": ["idempotency"]},
    {"key": "PAY-4", "concepts": []},
]


def test_load_issues_missing_directory_is_empty_not_an_error(tmp_path):
    assert load_issues(tmp_path / "does-not-exist") == []


def test_load_issues_empty_file_is_no_issues_found(tmp_path):
    (tmp_path / "issues.jsonl").write_text("", encoding="utf-8")
    assert load_issues(tmp_path) == []


def test_load_issues_skips_blank_lines(tmp_path):
    (tmp_path / "issues.jsonl").write_text('{"key": "A", "concepts": []}\n\n  \n', encoding="utf-8")
    assert load_issues(tmp_path) == [{"key": "A", "concepts": []}]


def test_citations_by_slug_is_every_tagging_issue_sorted():
    citations = citations_by_slug(ISSUES)
    assert citations["idempotency"] == ("PAY-1", "PAY-2")
    assert citations["retry-safety"] == ("PAY-1",)
    assert "double-entry" not in citations


def test_extract_concepts_is_every_concept_in_the_curated_doc_in_order():
    concepts = extract_concepts(ISSUES, CONCEPTS_DOC)
    assert [c.slug for c in concepts] == ["idempotency", "retry-safety", "double-entry"]
    assert [c.title for c in concepts] == ["Idempotency", "Retry safety", "Double entry"]
    assert next(c for c in concepts if c.slug == "double-entry").mastery_threshold == 0.9


def test_extract_concepts_citations_come_from_issues_not_the_curated_doc():
    concepts = {c.slug: c for c in extract_concepts(ISSUES, CONCEPTS_DOC)}
    assert concepts["idempotency"].citations == ("PAY-1", "PAY-2")
    assert concepts["double-entry"].citations == ()  # curated doc has this concept; no issue ever tagged it


def test_extract_edges_reads_both_kinds_from_the_curated_doc():
    edges = extract_edges(CONCEPTS_DOC)
    kinds = {(e.from_slug, e.to_slug): e.kind for e in edges}
    assert kinds == {("idempotency", "retry-safety"): "prerequisite", ("retry-safety", "double-entry"): "related"}
    related = next(e for e in edges if e.kind == "related")
    assert related.weight == 0.6


def test_extract_items_published_when_its_concept_has_a_traceable_citation():
    concepts = extract_concepts(ISSUES, CONCEPTS_DOC)
    items_doc = [{"concept": "idempotency", "slug": "i1", "kind": "mcq", "prompt": "?", "payload": {"options": []}}]
    (item,) = extract_items(items_doc, concepts)
    assert item.status == "published"
    assert item.payload["grounded_in"] == ["PAY-1", "PAY-2"]


def test_extract_items_draft_when_its_concept_has_no_traceable_citation():
    concepts = extract_concepts(ISSUES, CONCEPTS_DOC)
    items_doc = [{"concept": "double-entry", "slug": "i2", "kind": "mcq", "prompt": "?", "payload": {"options": []}}]
    (item,) = extract_items(items_doc, concepts)
    assert item.status == "draft"
    assert "grounded_in" not in item.payload


def test_extract_items_preserves_multiple_items_per_concept():
    concepts = extract_concepts(ISSUES, CONCEPTS_DOC)
    items_doc = [
        {"concept": "idempotency", "slug": "i1", "kind": "mcq", "prompt": "p1", "payload": {}},
        {"concept": "idempotency", "slug": "i2", "kind": "mcq", "prompt": "p2", "payload": {}},
    ]
    items = extract_items(items_doc, concepts)
    assert [i.prompt for i in items] == ["p1", "p2"]


def test_build_topics_one_per_persona_role_when_its_concepts_are_present():
    concepts = extract_concepts(
        [
            {"key": "A", "concepts": ["sca-exemptions"]},
            {"key": "B", "concepts": ["idempotency", "retry-safety"]},
            {"key": "C", "concepts": ["double-entry"]},
            {"key": "D", "concepts": ["payout-settlement"]},
            {"key": "E", "concepts": ["challenge-flow-ux"]},
        ],
        {
            "course": {"slug": "c", "title": "Course", "description": ""},
            "concepts": [
                {"slug": s, "title": s, "mastery_threshold": 0.85, "description": ""}
                for s in (
                    "sca-exemptions",
                    "idempotency",
                    "retry-safety",
                    "double-entry",
                    "payout-settlement",
                    "challenge-flow-ux",
                )
            ],
        },
    )
    topics = build_topics(concepts)
    assert {t.persona_role for t in topics} == {"pm", "uxd", "junior_swe", "senior_swe", "tech_lead"}
    for topic in topics:
        assert topic.entry_slug in topic.concept_slugs
        assert topic.grounded_in  # every topic must cite at least one real issue


def test_build_topics_skips_a_role_with_none_of_its_concepts_present():
    concepts = [ConceptDraft(slug="idempotency", title="Idempotency", description="", mastery_threshold=0.85, citations=("A",))]
    topics = build_topics(concepts)
    assert {t.persona_role for t in topics} == {"junior_swe"}


def test_seed_context_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("KATA_SEED_CONTEXT_DIR", str(tmp_path))
    assert seed_context_dir() == tmp_path


def test_seed_context_dir_default_resolves_to_the_vendored_web_data(monkeypatch):
    monkeypatch.delenv("KATA_SEED_CONTEXT_DIR", raising=False)
    resolved = seed_context_dir()
    assert resolved.parts[-4:] == ("src", "data", "seed-context", "1-context")
    assert (resolved / "issues.jsonl").exists()


def test_real_seed_produces_exactly_fourteen_concepts_matching_the_curated_doc():
    """The done check's own number: `seed_data/concepts.json` — the same
    file `learning_service/seed.py`'s golden-scenario loader uses — has
    exactly 14 concepts, and every one of them is tagged on at least one
    real seeded issue."""
    issues = load_issues(seed_context_dir())
    concepts = extract_concepts(issues, load_concepts_doc())
    assert len(concepts) == 14
    assert all(c.citations for c in concepts)


def test_real_seed_edges_match_the_curated_doc_and_are_acyclic_by_construction():
    edges = extract_edges(load_concepts_doc())
    assert len(edges) == 21  # 14 prerequisite + 7 related, per seed_data/concepts.json
    assert all(e.from_slug != e.to_slug for e in edges)


def test_real_seed_items_all_published_because_every_concept_has_a_citation():
    issues = load_issues(seed_context_dir())
    concepts = extract_concepts(issues, load_concepts_doc())
    items = extract_items(load_items_doc(), concepts)
    assert len(items) == 46
    assert all(i.status == "published" for i in items)
