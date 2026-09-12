"""`tools/registry.py::dispatch` pipes a plugin tool handler's return straight
into `_normalize_handler_result`, which accepts only `str` (or the
`_multimodal` envelope) — a bare dict/list/None is logged as an "unsupported
result type" and replaced with an error string instead of reaching the
model. Every forwarded `learning` tool must return a JSON string, never the
parsed object `LearningServiceClient.request` gives back internally.
"""

from __future__ import annotations

import json

import pytest
from fakes import FakeLearningServiceClient

from hermes_kata.client import ActingIdentity, LearningServiceError
from hermes_kata.tools import make_forwarder


def _identity_resolver(identity: ActingIdentity):
    return lambda **_: identity


def test_get_forwarder_returns_a_json_string_not_a_dict():
    client = FakeLearningServiceClient()
    client.set_response("GET", "/me/progress", {"concepts": [{"id": "c1", "mastery": 0.5}]})
    identity = ActingIdentity(platform="slack", external_id="U000")
    handler = make_forwarder(client, "GET", "/me/progress", resolve_identity=_identity_resolver(identity))

    result = handler({}, session_id="sess-1")

    assert isinstance(result, str)
    assert json.loads(result) == {"concepts": [{"id": "c1", "mastery": 0.5}]}


def test_post_forwarder_returns_a_json_string():
    client = FakeLearningServiceClient()
    client.set_response("POST", "/me/reviews", {"grade": 1.0, "correct": True})
    identity = ActingIdentity(platform="slack", external_id="U000")
    handler = make_forwarder(client, "POST", "/me/reviews", resolve_identity=_identity_resolver(identity))

    result = handler({"item_id": "i1", "idempotency_key": "k1", "response": {"choice": 1}}, session_id="sess-1")

    assert isinstance(result, str)
    assert json.loads(result) == {"grade": 1.0, "correct": True}


def test_forwarder_serializes_a_list_result():
    client = FakeLearningServiceClient()
    client.set_response("GET", "/me/notes", [{"text": "a"}, {"text": "b"}])
    identity = ActingIdentity(platform="slack", external_id="U000")
    handler = make_forwarder(client, "GET", "/me/notes", resolve_identity=_identity_resolver(identity))

    result = handler({}, session_id="sess-1")

    assert isinstance(result, str)
    assert json.loads(result) == [{"text": "a"}, {"text": "b"}]


def test_forwarder_serializes_a_none_result_for_a_204():
    client = FakeLearningServiceClient()
    client.set_response("DELETE", "/me/notes", None)
    identity = ActingIdentity(platform="slack", external_id="U000")
    handler = make_forwarder(client, "DELETE", "/me/notes", resolve_identity=_identity_resolver(identity))

    result = handler({}, session_id="sess-1")

    assert isinstance(result, str)
    assert json.loads(result) is None


def test_friendly_error_path_also_returns_a_json_string():
    client = FakeLearningServiceClient()
    client.set_error("GET", "/team/overview", LearningServiceError(403, "not_a_manager", "nope"))
    identity = ActingIdentity(platform="slack", external_id="U000")
    handler = make_forwarder(client, "GET", "/team/overview", resolve_identity=_identity_resolver(identity))

    result = handler({}, session_id="sess-1")

    assert isinstance(result, str)
    assert json.loads(result) == {"error": "that's not something I can show you"}


def test_unmapped_error_code_still_raises_not_swallowed_as_a_dict():
    client = FakeLearningServiceClient()
    client.set_error("GET", "/me/progress", LearningServiceError(500, "database_unreachable", "boom"))
    identity = ActingIdentity(platform="slack", external_id="U000")
    handler = make_forwarder(client, "GET", "/me/progress", resolve_identity=_identity_resolver(identity))

    with pytest.raises(LearningServiceError):
        handler({}, session_id="sess-1")


def test_path_params_are_substituted_and_excluded_from_the_serialized_body():
    client = FakeLearningServiceClient()
    client.set_response("DELETE", "/me/notes/abc-123", None)
    identity = ActingIdentity(platform="slack", external_id="U000")
    handler = make_forwarder(client, "DELETE", "/me/notes/{id}", resolve_identity=_identity_resolver(identity))

    handler({"id": "abc-123"}, session_id="sess-1")

    call = client.calls[-1]
    assert call["path"] == "/me/notes/abc-123"
    assert call["params"] is None
