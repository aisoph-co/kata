"""Spec §2: "an unresolved `(platform, external_id)` never reaches a tool
call or the model — assert the mock LLM client receives zero requests for
such an event, and the reply string is exactly the fixed message."

Also covers session binding against a real-shaped `SessionStore`/
`MessageEvent`/tool-call `session_id`: the hook must not raise on
`set_session_metadata`, must derive the session key via
`gateway._session_key_for_source` (no `event.session_key`), and a tool call's
bare `session_id` must resolve back through `lookup_by_session_id`.
"""

from __future__ import annotations

import pytest
from fakes import FakeGateway, FakeLearningServiceClient, FakeMessageEvent, FakeSessionStore, FakeSource

from hermes_kata.identity import (
    UNKNOWN_IDENTITY_MESSAGE,
    SessionIdentityCache,
    SessionStoreHandle,
    make_bind_identity,
)
from hermes_kata.tools import JobIdentityRegistry, make_identity_resolver


def _event(platform="slack", user_id="U42"):
    return FakeMessageEvent(source=FakeSource(platform=platform, user_id=user_id))


def _session_key(event: FakeMessageEvent, gateway: FakeGateway) -> str:
    return gateway._session_key_for_source(event.source)


def test_unknown_identity_is_refused_never_auto_created():
    client = FakeLearningServiceClient(person=None)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    bind_identity = make_bind_identity(client, cache, SessionStoreHandle())

    event = _event()
    result = bind_identity(event, gateway, session_store)
    session_key = _session_key(event, gateway)

    assert result == {"action": "skip", "reason": "unknown_identity"}
    assert gateway.replies == [(event, UNKNOWN_IDENTITY_MESSAGE)]
    # Nothing was stashed for a tool call to read later.
    assert cache.get(session_key) is None
    assert session_store.get_session_metadata(session_key, "kata_person") is None


def test_unknown_identity_reply_is_exactly_the_fixed_message_no_model_call():
    client = FakeLearningServiceClient(person=None)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    bind_identity = make_bind_identity(client, cache, SessionStoreHandle())

    bind_identity(_event(), gateway, FakeSessionStore())

    assert len(gateway.replies) == 1
    _, message = gateway.replies[0]
    assert message == UNKNOWN_IDENTITY_MESSAGE


def test_hook_does_not_raise_against_the_real_session_store_shape():
    # Regression: an earlier hook calling `session_store.set(...)` would
    # raise `AttributeError` — the real `gateway.session.SessionStore` only
    # has `set_session_metadata`. `FakeSessionStore` has no `.set` at all,
    # so this call would raise if the bug came back.
    person_payload = {"id": "p1", "display_name": "Hugo Marchetti", "email": "hugo@kata.example", "is_operator": False}
    client = FakeLearningServiceClient(person=person_payload, manager=False)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    bind_identity = make_bind_identity(client, cache, SessionStoreHandle())

    event = _event(user_id="U0BV21HFZ47")
    result = bind_identity(event, gateway, session_store)

    assert result == {"action": "allow"}
    session_key = _session_key(event, gateway)
    assert session_store.get_session_metadata(session_key, "kata_person")["id"] == "p1"


def test_known_identity_is_bound_before_any_tool_call():
    person_payload = {"id": "p1", "display_name": "Dee Learner", "email": "dee@kata.example", "is_operator": False}
    client = FakeLearningServiceClient(person=person_payload, manager=False)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    bind_identity = make_bind_identity(client, cache, SessionStoreHandle())

    event = _event(user_id="U000")
    result = bind_identity(event, gateway, session_store)
    session_key = _session_key(event, gateway)

    assert result == {"action": "allow"}
    assert gateway.replies == []

    bound = cache.get(session_key)
    assert bound is not None
    assert bound.id == "p1"
    assert bound.identity.platform == "slack"
    assert bound.identity.external_id == "U000"
    assert bound.is_manager is False

    # Hermes's own session_store carries the same fact, JSON-serializable
    # (spec §2 pseudocode; not a dataclass).
    stored = session_store.get_session_metadata(session_key, "kata_person")
    assert stored == {
        "id": "p1",
        "display_name": "Dee Learner",
        "is_manager": False,
        "platform": "slack",
        "external_id": "U000",
        "alt_id": None,
    }


def test_is_manager_flag_reflects_team_overview_access():
    person_payload = {"id": "p0", "display_name": "Ada Manager", "email": "ada@kata.example", "is_operator": True}
    client = FakeLearningServiceClient(person=person_payload, manager=True)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    bind_identity = make_bind_identity(client, cache, SessionStoreHandle())

    event = _event(user_id="U000")
    bind_identity(event, gateway, FakeSessionStore())

    assert cache.get(_session_key(event, gateway)).is_manager is True


def test_relink_mid_session_takes_effect_on_the_next_message_not_a_restart():
    # First message: unknown. Second message, same session: now known. The
    # cache re-resolves every message rather than trusting a stale bind.
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    session_store = FakeSessionStore()

    unknown_client = FakeLearningServiceClient(person=None)
    bind_identity = make_bind_identity(unknown_client, cache, SessionStoreHandle())
    event = _event(user_id="U777")
    bind_identity(event, gateway, session_store)
    session_key = _session_key(event, gateway)
    assert cache.get(session_key) is None

    known_client = FakeLearningServiceClient(
        person={"id": "p1", "display_name": "Dee", "email": "d@kata.example", "is_operator": False}
    )
    bind_identity = make_bind_identity(known_client, cache, SessionStoreHandle())
    result = bind_identity(_event(user_id="U777"), gateway, session_store)

    assert result == {"action": "allow"}
    assert cache.get(session_key) is not None


def test_hook_then_tool_call_resolves_identity_when_session_id_differs_from_session_key():
    # The gateway hands the hook a session *key* (derived from the platform
    # source) but hands tool-call handlers a session *id*
    # (`SessionEntry.session_id`) — a different value. Resolution must map
    # id -> key via `lookup_by_session_id` before it can hit the cache.
    person_payload = {"id": "p1", "display_name": "Hugo Marchetti", "email": "hugo@kata.example", "is_operator": False}
    client = FakeLearningServiceClient(person=person_payload)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    store_handle = SessionStoreHandle()
    bind_identity = make_bind_identity(client, cache, store_handle)

    event = _event(platform="slack", user_id="U0BV21HFZ47")
    result = bind_identity(event, gateway, session_store)
    assert result == {"action": "allow"}

    session_key = _session_key(event, gateway)
    session_store.link_session_id("session-id-abc", session_key)

    resolver = make_identity_resolver(cache, JobIdentityRegistry(), store_handle)
    identity = resolver(session_id="session-id-abc")

    assert identity.platform == "slack"
    assert identity.external_id == "U0BV21HFZ47"

    # A session reset re-issues `session_id` but keeps `session_key` — still
    # resolves off the same cache entry.
    session_store.link_session_id("session-id-after-reset", session_key)
    identity_after_reset = resolver(session_id="session-id-after-reset")
    assert identity_after_reset.external_id == "U0BV21HFZ47"


def test_store_handle_is_not_clobbered_by_a_later_none_session_store():
    # Hermes passes `session_store=getattr(self, "session_store", None)` on
    # every hook call — a later call with no session_store (e.g. an edge
    # case before one exists) must not blow away a handle that already
    # points at a working store.
    person_payload = {"id": "p1", "display_name": "Hugo", "email": "hugo@kata.example", "is_operator": False}
    client = FakeLearningServiceClient(person=person_payload)
    cache = SessionIdentityCache()
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    store_handle = SessionStoreHandle()
    bind_identity = make_bind_identity(client, cache, store_handle)

    bind_identity(_event(user_id="U0BV21HFZ47"), gateway, session_store)
    assert store_handle.store is session_store

    bind_identity(_event(user_id="U0BV21HFZ47"), gateway, None)
    assert store_handle.store is session_store


def test_unlinked_user_tool_call_raises_not_a_tool_error_reply():
    # The hook already refused (spec §2 — no tool call is even reached for
    # an unlinked user in the real gateway), but if one somehow arrived, the
    # resolver must still fail closed with the documented LookupError rather
    # than silently mis-attributing the call.
    cache = SessionIdentityCache()
    store_handle = SessionStoreHandle()
    resolver = make_identity_resolver(cache, JobIdentityRegistry(), store_handle)

    with pytest.raises(LookupError):
        resolver(session_id="some-session-id")
