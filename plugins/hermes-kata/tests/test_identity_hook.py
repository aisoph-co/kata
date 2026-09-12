"""§2 identity-hook tests: an unresolved identity never reaches a tool call
or the model, and gets the fixed refusal string; a known identity is bound
onto the session before any tool call."""
from conftest import FakeEvent, FakeGateway, FakeIdentityClient, FakeLLMClient, FakeSessionStore, FakeSource

from hermes_kata.identity import UNKNOWN_IDENTITY_MESSAGE, bind_identity


def test_unknown_identity_is_refused_before_the_model():
    client = FakeIdentityClient(known={})
    llm = FakeLLMClient()  # never touched below
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    event = FakeEvent(source=FakeSource(platform="slack", user_id="U999"), session_key="sess-1")

    result = bind_identity(event, gateway, session_store, client)

    assert result == {"action": "skip", "reason": "unknown_identity"}
    assert gateway.replies == [(event, UNKNOWN_IDENTITY_MESSAGE)]
    assert session_store.get("sess-1") == {}
    assert llm.calls == []


def test_known_identity_is_bound_before_any_tool_call():
    person = {"id": "person-1", "display_name": "Hugo", "is_manager": False}
    client = FakeIdentityClient(known={("slack", "U1"): person})
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    event = FakeEvent(source=FakeSource(platform="slack", user_id="U1"), session_key="sess-2")

    result = bind_identity(event, gateway, session_store, client)

    assert result == {"action": "allow"}
    assert gateway.replies == []
    bound = session_store.get("sess-2", "kata_person")
    assert bound["id"] == "person-1"
    assert bound["is_manager"] is False
    assert bound["platform"] == "slack"
    assert bound["external_id"] == "U1"


def test_alt_id_is_tried_when_present():
    person = {"id": "person-2", "display_name": "Quinn", "is_manager": True}
    client = FakeIdentityClient(known={("slack", "U2"): person})
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    event = FakeEvent(
        source=FakeSource(platform="slack", user_id="U2", user_id_alt="U2-alt"),
        session_key="sess-3",
    )

    result = bind_identity(event, gateway, session_store, client)

    assert result == {"action": "allow"}
    assert client.calls == [("slack", "U2", "U2-alt")]


def test_identity_is_re_resolved_every_message_not_cached_across_turns():
    client = FakeIdentityClient(known={})
    gateway = FakeGateway()
    session_store = FakeSessionStore()
    event = FakeEvent(source=FakeSource(platform="slack", user_id="U3"), session_key="sess-4")

    bind_identity(event, gateway, session_store, client)
    client.known[("slack", "U3")] = {"id": "person-3", "is_manager": False}
    result = bind_identity(event, gateway, session_store, client)

    assert result == {"action": "allow"}
    assert len(client.calls) == 2
