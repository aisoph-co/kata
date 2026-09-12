"""Grounding sources for CI1 extraction (`build-day/issues.md` "CI1",
KATA-13).

`load_context_issues` is the first, citation-accurate source: the seeded
`1-context/issues.jsonl` (vendored to `fixtures/ferry/issues.jsonl` per
`fixtures/ferry/SOURCE.md`). Lives here rather than in `ingestion.py` so
`learning_service.main` can build the stub `ExtractionClient`'s frequency
table from it without importing `ingestion.py` — which itself imports
`learning_service.main` (`require_operator`) and would deadlock the import
at module load. Re-exported from `ingestion.py` for that module's own call
sites (tests included).

`load_release_notes_source` is the second source: the seeded
`1-context/sprint-history.md` ("release notes"), vendored to
`fixtures/ferry/sprint-history.md`. It is also the closest thing this seed
gives ingestion to a third, "repo" source — real code identifiers
(`orchestrator`, `postings`, ...) the release notes name in backticks, not
fabricated ones. `augment_citations` folds both into a concept draft's
existing `grounded_in` list.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from importlib import resources
from typing import Any

_ISSUE_KEY_RE = re.compile(r"\bPAY-\d+[a-z]?\b")
_CODE_SPAN_RE = re.compile(r"`([A-Za-z_][\w./-]*)`")


def load_context_issues() -> list[dict[str, Any]]:
    """The seeded `1-context/issues.jsonl` grounding source. Missing or
    blank lines are skipped; an empty file yields `[]`, the "empty source"
    done-check case."""
    data = (
        resources.files("learning_service.fixtures")
        .joinpath("ferry")
        .joinpath("issues.jsonl")
        .read_text(encoding="utf-8")
    )
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def concept_frequency(issues: list[dict[str, Any]]) -> dict[str, int]:
    """How many distinct issues tag each concept slug — the only signal
    `extraction.stub.StubExtractionClient` has to guess prerequisite
    direction without reading either concept's meaning."""
    counts: Counter[str] = Counter()
    for issue in issues:
        counts.update(set(issue.get("concepts", [])))
    return dict(counts)


def _anchor(heading: str) -> str:
    """A citeable identifier for a `##` section, in the same
    `<file>#<anchor>` shape `Topic.grounded_in`'s docstring already
    documents (e.g. `sprint-history.md#sprint-42--stop-double-charging`).
    Not a strict GitHub-anchor implementation — just stable and readable."""
    slug = re.sub(r"[’'\"()]", "", heading.strip().lower())
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def load_release_notes_source() -> list[dict[str, Any]]:
    """One entry per `##` section of the seeded sprint history, each with
    the issue keys and repo-like identifiers it mentions. Missing file or
    no `##` sections yields `[]` — same empty-source contract as
    `load_context_issues`."""
    try:
        text = (
            resources.files("learning_service.fixtures")
            .joinpath("ferry")
            .joinpath("sprint-history.md")
            .read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        return []

    sections: list[dict[str, Any]] = []
    for block in re.split(r"(?m)^##\s+", text)[1:]:
        heading, _, body = block.partition("\n")
        issue_keys = sorted(set(_ISSUE_KEY_RE.findall(body)))
        repo_tokens = sorted({t for t in _CODE_SPAN_RE.findall(body) if not _ISSUE_KEY_RE.fullmatch(t)})
        sections.append(
            {
                "anchor": f"sprint-history.md#{_anchor(heading)}",
                "heading": heading.strip(),
                "issue_keys": issue_keys,
                "repo_tokens": repo_tokens,
            }
        )
    return sections


def augment_citations(
    drafts: list[dict[str, Any]], release_sections: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attaches a release-notes section to a concept draft when the section
    mentions an issue key the concept is already grounded in, plus up to
    two of that section's repo tokens as the concept's "repo" signal.
    Mutates and returns `drafts` for convenient chaining; a concept whose
    issue citations match no section is left exactly as it was (still
    traceable via its issue citations alone)."""
    for draft in drafts:
        cited_issue_keys = set(draft["grounded_in"])
        for section in release_sections:
            if not cited_issue_keys & set(section["issue_keys"]):
                continue
            if section["anchor"] not in draft["grounded_in"]:
                draft["grounded_in"].append(section["anchor"])
            for token in section["repo_tokens"][:2]:
                citation = f"repo:{token}"
                if citation not in draft["grounded_in"]:
                    draft["grounded_in"].append(citation)
    return drafts
