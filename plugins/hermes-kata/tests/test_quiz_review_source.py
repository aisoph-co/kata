"""Spec §6: a quiz-answer review must land `source = slack_thread`. The
reviewer's finding on the first pass (KATA-11): nothing asserted this
against the core's actual mapping, so a `platform="slack"` bug (source
lands `slack_dm` instead) went uncaught.

This reads `_SOURCE_BY_PLATFORM` out of `agency-v1/learning_service/
reviews.py`'s own source via `ast` (not a full import — that module pulls in
FastAPI/SQLAlchemy this plugin doesn't depend on) and asserts the pass-through
`quiz.py` relies on against the *real* dict, the same sibling-checkout
convention `test_tool_catalog_contract.py` already uses for `tools.json`.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

from hermes_kata.quiz import QUIZ_ANSWER_SOURCE_PLATFORM, quiz_answer_identity

REPO_ROOT = Path(__file__).resolve().parents[3]
LEARNING_SERVICE_SRC = Path(os.environ.get("LEARNING_SERVICE_SRC") or (REPO_ROOT.parent / "agency-v1"))
REVIEWS_PY = LEARNING_SERVICE_SRC / "learning_service" / "reviews.py"


def _source_by_platform() -> dict:
    tree = ast.parse(REVIEWS_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_SOURCE_BY_PLATFORM" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("_SOURCE_BY_PLATFORM not found in reviews.py — has it moved or been renamed?")


def test_reviews_py_exists_at_the_default_path():
    assert REVIEWS_PY.is_file()


def test_quiz_answer_source_platform_is_not_a_key_the_core_maps_elsewhere():
    # If a future contract change added `slack_thread` as a *key* (mapping
    # it to something else), the pass-through this plugin relies on would
    # silently produce the wrong source. Catches that drift here rather
    # than in a live demo.
    mapping = _source_by_platform()
    assert QUIZ_ANSWER_SOURCE_PLATFORM not in mapping


def test_quiz_answer_identity_platform_passes_through_to_slack_thread():
    mapping = _source_by_platform()
    identity = quiz_answer_identity("U0FERRY02")

    derived_source = mapping.get(identity.platform, identity.platform)

    assert derived_source == "slack_thread"


def test_a_learners_own_slack_platform_still_maps_to_slack_dm_not_thread():
    # Contrast case: an ordinary `submit_review` call from a learner's own
    # DM (tools.py's forwarder, real platform "slack") must NOT come out as
    # `slack_thread` — only a quiz answer's asserted identity does.
    mapping = _source_by_platform()
    assert mapping.get("slack", "slack") == "slack_dm"
