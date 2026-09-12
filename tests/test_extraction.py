"""CI1 (KATA-13) extraction layer: sources, the stub/real `ExtractionClient`
split, and the `Exa` no-op-without-a-key contract. No test here calls a
live model or makes a real network request (`httpx.MockTransport` covers
the real request/response contract that needs checking).
"""

from __future__ import annotations

import json

import httpx
import pytest

from learning_service.extraction.client import (
    DEFAULT_MODEL,
    ExtractionError,
    OpenRouterExtractionClient,
)
from learning_service.extraction.exa import ExaClient
from learning_service.extraction.sources import (
    augment_citations,
    concept_frequency,
    load_release_notes_source,
)
from learning_service.extraction.stub import StubExtractionClient

ISSUES = [
    {"key": "PAY-1", "concepts": ["idempotency", "retry-safety"]},
    {"key": "PAY-2", "concepts": ["idempotency"]},
    {"key": "PAY-3", "concepts": ["retry-safety"]},
    {"key": "PAY-4", "concepts": ["retry-safety"]},
]

_RealAsyncClient = httpx.AsyncClient


def _mock_async_client(handler):
    def factory(**kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


# ---------------------------------------------------------------------------
# sources.py
# ---------------------------------------------------------------------------


def test_concept_frequency_counts_distinct_issues_per_slug():
    assert concept_frequency(ISSUES) == {"idempotency": 2, "retry-safety": 3}


def test_concept_frequency_counts_a_slug_once_per_issue_even_if_repeated():
    assert concept_frequency([{"key": "PAY-1", "concepts": ["idempotency", "idempotency"]}]) == {"idempotency": 1}


def test_load_release_notes_source_parses_the_seeded_sprint_history():
    # `fixtures/ferry/sprint-history.md`, vendored from `docs/seed/
    # 1-context/sprint-history.md` per `fixtures/ferry/SOURCE.md`.
    sections = load_release_notes_source()
    assert len(sections) > 0
    assert all(s["anchor"].startswith("sprint-history.md#") for s in sections)

    sprint_42 = next(s for s in sections if "sprint-42" in s["anchor"])
    assert "PAY-1841" in sprint_42["issue_keys"]
    assert "PAY-1863" in sprint_42["issue_keys"]
    assert "orchestrator" in sprint_42["repo_tokens"]


def test_augment_citations_adds_section_anchor_and_repo_tokens_on_issue_key_match():
    drafts = [{"slug": "idempotency", "title": "Idempotency", "grounded_in": ["PAY-1841"]}]
    sections = [
        {
            "anchor": "sprint-history.md#sprint-42",
            "heading": "Sprint 42",
            "issue_keys": ["PAY-1841", "PAY-1847"],
            "repo_tokens": ["orchestrator", "postings", "add_posting_currency"],
        }
    ]
    augment_citations(drafts, sections)
    assert drafts[0]["grounded_in"] == [
        "PAY-1841",
        "sprint-history.md#sprint-42",
        "repo:orchestrator",
        "repo:postings",
    ]


def test_augment_citations_ignores_a_section_that_shares_no_issue_key():
    drafts = [{"slug": "idempotency", "title": "Idempotency", "grounded_in": ["PAY-1841"]}]
    sections = [{"anchor": "sprint-history.md#other", "heading": "Other", "issue_keys": ["PAY-9999"], "repo_tokens": ["x"]}]
    augment_citations(drafts, sections)
    assert drafts[0]["grounded_in"] == ["PAY-1841"]


def test_augment_citations_does_not_duplicate_an_already_present_citation():
    drafts = [{"slug": "idempotency", "title": "Idempotency", "grounded_in": ["PAY-1841", "repo:orchestrator"]}]
    sections = [
        {
            "anchor": "sprint-history.md#sprint-42",
            "heading": "Sprint 42",
            "issue_keys": ["PAY-1841"],
            "repo_tokens": ["orchestrator"],
        }
    ]
    augment_citations(drafts, sections)
    assert drafts[0]["grounded_in"].count("repo:orchestrator") == 1


# ---------------------------------------------------------------------------
# stub.py
# ---------------------------------------------------------------------------


def _draft(slug: str, grounded_in: list[str] | None = None) -> dict:
    return {"slug": slug, "title": slug.replace("-", " ").title(), "description": f"about {slug}", "grounded_in": grounded_in or []}


async def test_stub_classify_relation_makes_the_more_discussed_concept_the_prerequisite():
    client = StubExtractionClient({"idempotency": 2, "retry-safety": 4})
    relation = await client.classify_relation(concept_a=_draft("idempotency"), concept_b=_draft("retry-safety"))
    assert relation == {"kind": "prerequisite", "from_slug": "retry-safety", "to_slug": "idempotency", "weight": 1.0}


async def test_stub_classify_relation_ties_stay_related():
    client = StubExtractionClient({"a": 2, "b": 2})
    relation = await client.classify_relation(concept_a=_draft("a"), concept_b=_draft("b"))
    assert relation["kind"] == "related"
    assert 0 < relation["weight"] <= 1


async def test_stub_draft_item_returns_none_for_an_untraceable_concept():
    client = StubExtractionClient({})
    assert await client.draft_item(concept=_draft("mystery"), distractor_pool=["Idempotency"]) is None


async def test_stub_draft_item_uses_the_concept_title_as_the_correct_option():
    client = StubExtractionClient({})
    concept = _draft("idempotency", grounded_in=["PAY-1"])
    item = await client.draft_item(concept=concept, distractor_pool=["Retry safety", "Double entry", "Reconciliation"])
    assert item["kind"] == "mcq"
    assert len(item["options"]) == 4
    assert item["options"][item["correct_index"]] == "Idempotency"
    assert "PAY-1" in item["prompt"]


# ---------------------------------------------------------------------------
# client.py — OpenRouterExtractionClient
# ---------------------------------------------------------------------------


async def test_missing_api_key_raises_extraction_error_for_both_methods():
    client = OpenRouterExtractionClient(api_key="")
    with pytest.raises(ExtractionError):
        await client.classify_relation(concept_a=_draft("a"), concept_b=_draft("b"))
    with pytest.raises(ExtractionError):
        await client.draft_item(concept=_draft("a", grounded_in=["PAY-1"]), distractor_pool=[])


def test_default_model_unchanged_without_env(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    client = OpenRouterExtractionClient(api_key="k")
    assert client._model == DEFAULT_MODEL == "openai/gpt-4o-mini"


async def test_classify_relation_parses_json_content_and_floors_weight_above_zero(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        content = json.dumps({"kind": "related", "from_slug": "a", "to_slug": "b", "weight": 0.0})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_async_client(handler))
    client = OpenRouterExtractionClient(api_key="test-key")
    relation = await client.classify_relation(concept_a=_draft("a"), concept_b=_draft("b"))
    assert relation["kind"] == "related"
    assert relation["weight"] > 0  # never exactly 0 — `create_edge` rejects a related weight of 0


async def test_classify_relation_raises_on_malformed_payload(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps({"kind": "related"})  # missing from_slug/to_slug/weight
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_async_client(handler))
    client = OpenRouterExtractionClient(api_key="test-key")
    with pytest.raises(ExtractionError):
        await client.classify_relation(concept_a=_draft("a"), concept_b=_draft("b"))


async def test_draft_item_returns_none_without_grounded_in(monkeypatch):
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_async_client(handler))
    client = OpenRouterExtractionClient(api_key="test-key")
    assert await client.draft_item(concept=_draft("a"), distractor_pool=[]) is None
    assert not called  # no citation, no request made


async def test_draft_item_parses_four_options(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps(
            {
                "prompt": "What is idempotency?",
                "options": ["A", "B", "C", "D"],
                "correct_index": 2,
                "explanation": "because",
            }
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_async_client(handler))
    client = OpenRouterExtractionClient(api_key="test-key")
    item = await client.draft_item(concept=_draft("a", grounded_in=["PAY-1"]), distractor_pool=[])
    assert item == {
        "kind": "mcq",
        "prompt": "What is idempotency?",
        "options": ["A", "B", "C", "D"],
        "correct_index": 2,
        "explanation": "because",
    }


# ---------------------------------------------------------------------------
# exa.py
# ---------------------------------------------------------------------------


async def test_exa_search_is_a_noop_without_an_api_key():
    client = ExaClient(api_key="")
    assert await client.search("anything") is None
