"""KATA-14: the api_server identity gate.

`api_server` (the web popup's Hermes surface) never fires
`pre_gateway_dispatch` at all (see `identity.py`'s module docstring for how
that was confirmed against the exact commit the deployed image is built
from), so `install_api_server_identity_gate` patches
`APIServerAdapter._run_agent` directly. These tests fake
`gateway.platforms.api_server` itself — the point is the patch's own
behavior (resolve-or-refuse, cache lifecycle, zero-LLM-call refusal), not
re-testing hermes-agent's internals.
"""

from __future__ import annotations

import asyncio
import sys
import types

import pytest
from fakes import FakeLearningServiceClient

from hermes_kata.identity import (
    UNKNOWN_IDENTITY_MESSAGE,
    SessionIdentityCache,
    install_api_server_identity_gate,
    with_api_server_fallback,
)
from hermes_kata.tools import JobIdentityRegistry, make_identity_resolver


class _FakeAPIServerAdapter:
    """Stands in for the real `APIServerAdapter` — just enough surface for
    the patch to grab (`_run_agent`) and call back into (`self`)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def _run_agent(self, **kwargs):
        # The real method's actual work: build an AIAgent and run a turn,
        # during which a tool call resolves identity via
        # tools.py's resolver — recording that here (through the same
        # api_server_cache the fixture below wires up) proves the cache is
        # live for exactly the window a real tool call would see it.
        self.calls.append(kwargs)
        return (
            {"final_response": "the real answer", "completed": True, "session_id": kwargs.get("session_id")},
            {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
        )


@pytest.fixture
def fake_api_server_module(monkeypatch):
    """Install a fake `gateway.platforms.api_server` module — a fresh
    `_Adapter` subclass per test, since `install_api_server_identity_gate`
    patches the class attribute in place and a shared class would leak one
    test's patch into the next."""

    class _Adapter(_FakeAPIServerAdapter):
        pass

    module = types.ModuleType("gateway.platforms.api_server")
    module.APIServerAdapter = _Adapter
    monkeypatch.setitem(sys.modules, "gateway", sys.modules.get("gateway") or types.ModuleType("gateway"))
    monkeypatch.setitem(
        sys.modules, "gateway.platforms", sys.modules.get("gateway.platforms") or types.ModuleType("gateway.platforms")
    )
    monkeypatch.setitem(sys.modules, "gateway.platforms.api_server", module)
    return module


def test_returns_false_when_api_server_platform_is_not_loaded(monkeypatch):
    # No real Hermes install in this test environment — `gateway.platforms`
    # genuinely doesn't exist, exactly like a Slack-only/CLI-only Hermes
    # process that never loads the api_server platform adapter.
    monkeypatch.delitem(sys.modules, "gateway.platforms.api_server", raising=False)
    monkeypatch.delitem(sys.modules, "gateway.platforms", raising=False)
    monkeypatch.delitem(sys.modules, "gateway", raising=False)

    assert install_api_server_identity_gate(FakeLearningServiceClient(), SessionIdentityCache()) is False


def test_returns_false_when_run_agent_is_missing(fake_api_server_module):
    # `_run_agent` is inherited from `_FakeAPIServerAdapter`; shadow it with
    # `None` on the subclass rather than `del` (which only works on an
    # attribute the subclass itself defines) to simulate "not present".
    fake_api_server_module.APIServerAdapter._run_agent = None

    assert install_api_server_identity_gate(FakeLearningServiceClient(), SessionIdentityCache()) is False


def test_known_identity_passes_through_and_caches_for_the_call(fake_api_server_module):
    person_payload = {"id": "p1", "display_name": "Hugo", "email": "hugo@kata.example", "is_operator": False}
    client = FakeLearningServiceClient(person=person_payload, manager=False)
    cache = SessionIdentityCache()

    assert install_api_server_identity_gate(client, cache) is True

    adapter = fake_api_server_module.APIServerAdapter()

    result, usage = asyncio.run(
        adapter._run_agent(
            session_id="sid-1", gateway_session_key="web:hugo@ferry.example",
            user_message="hi", conversation_history=[],
        )
    )

    assert result == {"final_response": "the real answer", "completed": True, "session_id": "sid-1"}
    assert usage == {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8}
    assert adapter.calls[0]["session_id"] == "sid-1"
    # Cleaned up after the call — never leaks to the next request on a
    # reused thread/adapter.
    assert cache.get("sid-1") is None


def test_a_tool_call_mid_run_resolves_via_the_composed_resolver(fake_api_server_module):
    """The end-to-end path a real learning-tool call takes: the gate caches
    identity for the call's `session_id` before delegating, and
    `with_api_server_fallback`'s resolver (what `tools.py`'s handlers
    actually call, mid-turn) reads it back — without ever touching the
    gateway's own `SessionIdentityCache`/`SessionStoreHandle`, which an
    api_server turn never populates."""
    from hermes_kata.identity import SessionStoreHandle

    person_payload = {"id": "p1", "display_name": "Hugo", "email": "hugo@kata.example", "is_operator": False}
    client = FakeLearningServiceClient(person=person_payload)
    api_server_cache = SessionIdentityCache()
    gateway_resolver = make_identity_resolver(SessionIdentityCache(), JobIdentityRegistry(), SessionStoreHandle())
    resolve = with_api_server_fallback(gateway_resolver, api_server_cache)

    seen_identity = {}

    class _ResolvingAdapter(_FakeAPIServerAdapter):
        async def _run_agent(self, **kwargs):
            # Stands in for a tool call happening mid-turn, inside the real
            # `agent.run_conversation(...)` this method would otherwise run.
            seen_identity["identity"] = resolve(session_id=kwargs.get("session_id"))
            return await super()._run_agent(**kwargs)

    fake_api_server_module.APIServerAdapter = _ResolvingAdapter
    assert install_api_server_identity_gate(client, api_server_cache) is True
    adapter = fake_api_server_module.APIServerAdapter()

    asyncio.run(adapter._run_agent(session_id="sid-mid-call", gateway_session_key="web:hugo@ferry.example"))

    assert seen_identity["identity"].platform == "web"
    assert seen_identity["identity"].external_id == "hugo@ferry.example"


def test_unknown_identity_never_reaches_the_original_run_agent(fake_api_server_module):
    client = FakeLearningServiceClient(person=None)
    cache = SessionIdentityCache()
    assert install_api_server_identity_gate(client, cache) is True
    adapter = fake_api_server_module.APIServerAdapter()

    result, usage = asyncio.run(
        adapter._run_agent(session_id="sid-2", gateway_session_key="web:nobody@ferry.example")
    )

    assert result == {"final_response": UNKNOWN_IDENTITY_MESSAGE, "completed": True, "session_id": "sid-2"}
    assert usage == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    assert adapter.calls == []  # the original (which would build an AIAgent) was never called


def test_unknown_identity_streams_the_refusal_text_as_a_single_delta(fake_api_server_module):
    client = FakeLearningServiceClient(person=None)
    cache = SessionIdentityCache()
    assert install_api_server_identity_gate(client, cache) is True
    adapter = fake_api_server_module.APIServerAdapter()
    deltas: list[str] = []

    asyncio.run(
        adapter._run_agent(
            session_id="sid-3", gateway_session_key="web:nobody@ferry.example",
            stream_delta_callback=deltas.append,
        )
    )

    # The SSE writer only ever forwards text pushed through this callback —
    # `final_response` alone is invisible to a streaming caller (CopilotKit).
    assert deltas == [UNKNOWN_IDENTITY_MESSAGE]


def test_malformed_session_key_is_treated_as_unknown(fake_api_server_module):
    client = FakeLearningServiceClient(person=None)
    cache = SessionIdentityCache()
    assert install_api_server_identity_gate(client, cache) is True
    adapter = fake_api_server_module.APIServerAdapter()

    result, _ = asyncio.run(adapter._run_agent(session_id="sid-4", gateway_session_key="no-colon-here"))

    assert result["final_response"] == UNKNOWN_IDENTITY_MESSAGE


def test_with_api_server_fallback_never_shadows_a_real_gateway_resolution():
    """A gateway-platform session_id resolves via the real cache/store path
    exactly as before — the api_server cache is only ever consulted after
    that raises, never instead of it."""
    from hermes_kata.identity import BoundPerson
    from hermes_kata.client import ActingIdentity

    gateway_cache = SessionIdentityCache()
    gateway_cache.set(
        "slack:U1",
        BoundPerson(id="p1", display_name="Hugo", identity=ActingIdentity(platform="slack", external_id="U1"), is_manager=False),
    )

    class _StubStoreHandle:
        store = None

    def fake_resolver(*, session_id=None, job_name=None, **_):
        if session_id == "gateway-session":
            return gateway_cache.get("slack:U1").identity
        raise LookupError("no bound identity")

    api_server_cache = SessionIdentityCache()
    api_server_cache.set(
        "api-server-session",
        BoundPerson(id="p2", display_name="Dee", identity=ActingIdentity(platform="web", external_id="dee@x.com"), is_manager=False),
    )

    resolve = with_api_server_fallback(fake_resolver, api_server_cache)

    assert resolve(session_id="gateway-session").external_id == "U1"
    assert resolve(session_id="api-server-session").external_id == "dee@x.com"

    with pytest.raises(LookupError):
        resolve(session_id="neither")
