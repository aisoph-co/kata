"""AGCTM-69 fix-round 2: `platform="slack_thread"` alone 403s
`unknown_identity` against a real roster-imported DB — `resolve_identity`
needs a matching `Identity` row, and roster import only ever creates one
with `platform="slack"`. `ensure_quiz_thread_identity` closes that gap via
the link-code pair already in the frozen `tools.json`.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
from fakes import FakeLearningServiceClient

from hermes_kata.client import LearningServiceError
from hermes_kata.quiz import (
    QUIZ_ANSWER_SOURCE_PLATFORM,
    _ALREADY_LINKED_MESSAGE,
    ensure_quiz_thread_identity,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
LEARNING_SERVICE_SRC = Path(os.environ.get("LEARNING_SERVICE_SRC") or (REPO_ROOT.parent / "agency-v1"))
MAIN_PY = LEARNING_SERVICE_SRC / "learning_service" / "main.py"


def test_links_via_the_learners_own_slack_identity_then_the_new_slack_thread_one():
    client = FakeLearningServiceClient()
    client.set_response("POST", "/me/link-code", {"code": "code-123"})
    client.set_response("POST", "/identities/link", None)

    ensure_quiz_thread_identity(client, "U0FERRY02")

    link_code_call = client.calls[0]
    assert link_code_call["method"] == "POST"
    assert link_code_call["path"] == "/me/link-code"
    assert link_code_call["identity"].platform == "slack"
    assert link_code_call["identity"].external_id == "U0FERRY02"

    link_call = client.calls[1]
    assert link_call["method"] == "POST"
    assert link_call["path"] == "/identities/link"
    assert link_call["json_body"] == {
        "code": "code-123",
        "platform": QUIZ_ANSWER_SOURCE_PLATFORM,
        "external_id": "U0FERRY02",
    }


def test_never_bridges_platforms_via_alt_id():
    # `identity/service.py`'s `resolve_identity` filters `alt_id` lookups by
    # `platform` too, so putting `slack_thread` in `alt_id` on the `slack`
    # link-code request would not help — assert this call never does that.
    client = FakeLearningServiceClient()
    client.set_response("POST", "/me/link-code", {"code": "code-123"})
    client.set_response("POST", "/identities/link", None)

    ensure_quiz_thread_identity(client, "U0FERRY02")

    assert client.calls[0]["identity"].alt_id is None


def test_an_already_linked_identity_is_treated_as_success_not_an_error():
    client = FakeLearningServiceClient()
    client.set_response("POST", "/me/link-code", {"code": "code-123"})
    client.set_error(
        "POST", "/identities/link", LearningServiceError(422, "validation_error", _ALREADY_LINKED_MESSAGE)
    )

    ensure_quiz_thread_identity(client, "U0FERRY02")  # must not raise


def test_a_different_validation_error_still_raises():
    client = FakeLearningServiceClient()
    client.set_response("POST", "/me/link-code", {"code": "code-123"})
    client.set_error(
        "POST", "/identities/link", LearningServiceError(422, "validation_error", "some other problem entirely")
    )

    with pytest.raises(LearningServiceError):
        ensure_quiz_thread_identity(client, "U0FERRY02")


def test_an_invalid_link_code_error_still_raises():
    client = FakeLearningServiceClient(person=None)
    client.set_error("POST", "/me/link-code", LearningServiceError(403, "unknown_identity", "no person matches"))

    with pytest.raises(LearningServiceError):
        ensure_quiz_thread_identity(client, "U0FERRY02")


def test_main_py_exists_at_the_default_path():
    assert MAIN_PY.is_file()


def test_already_linked_message_matches_the_real_source_exactly():
    """Guards `_ALREADY_LINKED_MESSAGE` against silent drift: reads the
    literal string `main.py` raises from its own `except
    IdentityAlreadyLinked` handler for `POST /identities/link` via `ast`
    (no FastAPI/SQLAlchemy import needed) rather than trusting a copy."""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    messages = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            type_name = node.type.id if isinstance(node.type, ast.Name) else None
            if type_name != "IdentityAlreadyLinked":
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id == "_error"
                    and len(inner.args) >= 3
                    and isinstance(inner.args[2], ast.Constant)
                ):
                    messages.add(inner.args[2].value)
    assert messages == {_ALREADY_LINKED_MESSAGE}
