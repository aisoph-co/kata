"""Job 1 (adapter-contract): bind identity.

`pre_gateway_dispatch` hook (spec §2). Fires once per inbound `MessageEvent`,
before auth/pairing and before the agent turn starts — the only hook that can
refuse a message before Hermes does anything else with it (spec "Decisions",
"Identity-binding hook").

`install_api_server_identity_gate` (KATA-14) binds identity for the
`api_server` platform (the web popup's Hermes surface) instead, because
`pre_gateway_dispatch` never fires for it at all: confirmed directly against
the exact commit the deployed image is built from (`ARG HERMES_GIT_SHA` in
`deploy/kata/hermes/Dockerfile`'s pinned image, checked out from
github.com/NousResearch/hermes-agent) — `gateway/platforms/
api_server_openai_routes.py`'s route handlers call `APIServerAdapter.
_run_agent` directly, never `GatewayRunner._handle_message`, the only place
that fires the hook. `hermes-agent` is NousResearch's own third-party
package (MIT-licensed, not a repo this workspace owns), so there is no
same-day upstream PR or pinned fork to land ahead of this issue's deploy —
this installs the identical resolve-or-refuse contract directly onto the
one platform adapter that never reaches it, entirely from this plugin's own
`register(ctx)` call, no image or pin change.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Optional

from .client import ActingIdentity, LearningServiceClient

logger = logging.getLogger(__name__)

UNKNOWN_IDENTITY_MESSAGE = (
    "You're not set up as a Kata learner yet — ask your team admin for an invite."
)

# Also the key `tools.py`'s resolver reads back with `get_session_metadata`
# when the plugin cache has missed (session survived a plugin reload/restart).
SESSION_METADATA_KEY = "kata_person"


@dataclass(frozen=True)
class BoundPerson:
    id: str
    display_name: str
    identity: ActingIdentity
    is_manager: bool


def person_to_metadata(person: BoundPerson) -> dict:
    """`set_session_metadata` needs a JSON-serializable value, not a
    dataclass — flatten `identity` alongside the rest."""
    return {
        "id": person.id,
        "display_name": person.display_name,
        "is_manager": person.is_manager,
        "platform": person.identity.platform,
        "external_id": person.identity.external_id,
        "alt_id": person.identity.alt_id,
    }


def person_from_metadata(data: Optional[dict]) -> Optional[BoundPerson]:
    if not data:
        return None
    identity = ActingIdentity(
        platform=data["platform"], external_id=data["external_id"], alt_id=data.get("alt_id")
    )
    return BoundPerson(
        id=data["id"], display_name=data["display_name"], identity=identity, is_manager=data.get("is_manager", False)
    )


class SessionStoreHandle:
    """Holds the live `session_store` the gateway hands `pre_gateway_dispatch`
    on every inbound message. `tools.py`'s resolver only receives a bare
    `session_id` (no `session_store`), so it reaches the same store through
    this handle instead of a second wiring path."""

    def __init__(self) -> None:
        self.store: Any = None

    def set(self, session_store: Any) -> None:
        # Hermes passes `session_store=getattr(self, "session_store", None)`
        # on every hook call — a `None` on some later call must not clobber
        # an already-live store.
        if session_store is not None:
            self.store = session_store


def session_key_for_session_id(store_handle: SessionStoreHandle, session_id: Optional[str]) -> Optional[str]:
    """Maps a session's *id* (`SessionEntry.session_id`) back to its *key*
    (what the identity cache and `session_store` metadata are keyed by) via
    `session_store.lookup_by_session_id`. `tools.py`'s tool-call resolution
    only ever receives a session id, never the key directly."""
    if session_id is None or store_handle.store is None:
        return None
    lookup = getattr(store_handle.store, "lookup_by_session_id", None)
    if lookup is None:
        return None
    entry = lookup(session_id)
    return getattr(entry, "session_key", None) if entry is not None else None


class SessionIdentityCache:
    """Per-session bound-identity cache (spec §2: "cached in `session_store`
    keyed by `event.session_key` so tool-call handlers in the same turn read
    it without a second resolve call").

    Re-set on every message, never carried across a session restart — a
    link/unlink takes effect on the learner's very next message.
    """

    def __init__(self) -> None:
        self._data: dict[str, BoundPerson] = {}
        self._lock = threading.Lock()

    def set(self, session_key: str, person: BoundPerson) -> None:
        with self._lock:
            self._data[session_key] = person

    def get(self, session_key: Optional[str]) -> Optional[BoundPerson]:
        if not session_key:
            return None
        with self._lock:
            return self._data.get(session_key)

    def clear(self, session_key: str) -> None:
        with self._lock:
            self._data.pop(session_key, None)


def _resolve_bound_person(
    client: LearningServiceClient, platform: str, external_id: str, alt_id: Optional[str]
) -> Optional[BoundPerson]:
    person = client.resolve_identity(platform, external_id, alt_id)
    if person is None:
        return None
    identity = ActingIdentity(platform=platform, external_id=external_id, alt_id=alt_id)
    return BoundPerson(
        id=person["id"],
        display_name=person["display_name"],
        identity=identity,
        is_manager=client.is_manager(identity),
    )


def _session_key_for_event(event: Any, gateway: Any) -> Optional[str]:
    """The real `gateway.platforms.base.MessageEvent` has no `session_key`
    field — the gateway derives it from `event.source` via
    `gateway._session_key_for_source` (`gateway/run.py`). Fall back to an
    attribute directly on the event only if the gateway doesn't expose the
    computer (e.g. a minimal stub)."""
    compute = getattr(gateway, "_session_key_for_source", None)
    if compute is not None:
        return compute(event.source)
    return getattr(event, "session_key", None)


def make_bind_identity(
    client: LearningServiceClient, cache: SessionIdentityCache, store_handle: SessionStoreHandle
):
    """Build the `pre_gateway_dispatch` callback (spec §2 pseudocode).

    Kwargs match the hook's documented contract: `event: MessageEvent,
    gateway: GatewayRunner, session_store` (hermes_cli/plugins.py `VALID_HOOKS`
    entry for `pre_gateway_dispatch`). `session_store` is `gateway.session.
    SessionStore` — `set_session_metadata`/`get_session_metadata`, not a
    dict-like `.set`/`.get`. This hook fires before auth/dispatch, so the
    session entry `set_session_metadata` writes into may not exist yet on a
    session's first message; write it best-effort and treat `cache` (this
    plugin's own mirror, keyed by session key) as the source of truth that
    tool-call handlers actually read (see tools.py).
    """

    def bind_identity(event: Any, gateway: Any, session_store: Any, **_: Any) -> dict:
        store_handle.set(session_store)
        source = event.source
        platform = source.platform.value if hasattr(source.platform, "value") else source.platform
        external_id = source.user_id
        alt_id = getattr(source, "user_id_alt", None)
        session_key = _session_key_for_event(event, gateway)

        person = _resolve_bound_person(client, platform, external_id, alt_id)
        if person is None:
            gateway.send_reply(event, UNKNOWN_IDENTITY_MESSAGE)
            return {"action": "skip", "reason": "unknown_identity"}

        if session_key is not None:
            try:
                session_store.set_session_metadata(session_key, SESSION_METADATA_KEY, person_to_metadata(person))
            except Exception:
                pass  # best-effort; the plugin cache below is what tool calls read
            cache.set(session_key, person)
        return {"action": "allow"}

    return bind_identity


def register_identity_hook(
    ctx: Any, client: LearningServiceClient, cache: SessionIdentityCache, store_handle: SessionStoreHandle
) -> None:
    ctx.register_hook("pre_gateway_dispatch", make_bind_identity(client, cache, store_handle))


# ---------------------------------------------------------------------------
# api_server identity gate (KATA-14) — see module docstring for why this
# exists as a monkeypatch rather than a `pre_gateway_dispatch` registration.
# ---------------------------------------------------------------------------


def resolve_api_server_identity(
    client: LearningServiceClient, gateway_session_key: str
) -> Optional[BoundPerson]:
    """Resolve the identity for an api_server turn from the
    `X-Hermes-Session-Key` value the Node runtime stamps
    (`web/server/index.ts`): `"<platform>:<external_id>"`, e.g.
    `"web:hugo@ferry.example"`. A key with no `:` (or an empty platform/id)
    can't be anyone's identity."""
    platform, sep, external_id = gateway_session_key.partition(":")
    if not sep or not platform or not external_id:
        return None
    try:
        return _resolve_bound_person(client, platform, external_id, None)
    except Exception:
        # A Learning Service hiccup must fail closed (refuse), never let an
        # unresolved caller through as if they were known.
        logger.exception("hermes-kata: identity resolve failed for an api_server turn")
        return None


def install_api_server_identity_gate(client: LearningServiceClient, cache: SessionIdentityCache) -> bool:
    """Monkeypatch `APIServerAdapter._run_agent` — the single choke point
    every api_server route that produces text calls (`/v1/chat/completions`
    streaming and non-streaming, `/v1/responses`, session chat) — to
    resolve identity from `gateway_session_key` before any `AIAgent` is
    built, mirroring `bind_identity`'s resolve-or-refuse contract exactly.

    Returns True once patched. Returns False (after logging why) when the
    installed `hermes-agent` doesn't expose `_run_agent` in the expected
    shape — e.g. a future upgrade renamed/restructured it. Fails closed
    either way: `tools.py`'s resolver still raises "no bound identity" for
    every api_server tool call when this hasn't run, rather than silently
    trusting an unresolved caller.
    """
    try:
        from gateway.platforms import api_server as _api_server_module
    except ImportError:
        logger.debug(
            "hermes-kata: gateway.platforms.api_server not importable — "
            "api_server platform not enabled in this process, nothing to patch"
        )
        return False

    adapter_cls = getattr(_api_server_module, "APIServerAdapter", None)
    original_run_agent = getattr(adapter_cls, "_run_agent", None)
    if adapter_cls is None or original_run_agent is None:
        logger.error(
            "hermes-kata: gateway.platforms.api_server.APIServerAdapter._run_agent not found — "
            "installed hermes-agent has changed shape; api_server identity gate NOT installed, "
            "every api_server learning-tool call will fail closed with 'no bound identity'"
        )
        return False

    async def _patched_run_agent(self: Any, *args: Any, **kwargs: Any) -> tuple:
        session_id = kwargs.get("session_id") or ""
        gateway_session_key = kwargs.get("gateway_session_key") or ""
        cache_key = (session_id or gateway_session_key).strip()
        lookup_key = (gateway_session_key or session_id).strip()

        person = resolve_api_server_identity(client, lookup_key) if lookup_key else None
        if person is None:
            # Zero LLM calls: return the same shape a completed run would,
            # so the OpenAI-format response the popup sees is a normal
            # assistant message, not an error envelope.
            stream_delta_callback = kwargs.get("stream_delta_callback")
            if stream_delta_callback is not None:
                # A streaming caller (CopilotKit's OpenAIAdapter) only ever
                # renders text pushed through this callback — the
                # non-streaming `final_response` field below is never
                # re-emitted as a delta by the SSE writer.
                stream_delta_callback(UNKNOWN_IDENTITY_MESSAGE)
            return (
                {"final_response": UNKNOWN_IDENTITY_MESSAGE, "completed": True, "session_id": session_id},
                {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            )

        if cache_key:
            cache.set(cache_key, person)
        try:
            return await original_run_agent(self, *args, **kwargs)
        finally:
            if cache_key:
                cache.clear(cache_key)

    adapter_cls._run_agent = _patched_run_agent
    logger.info("hermes-kata: api_server identity gate installed (KATA-14)")
    return True


def with_api_server_fallback(resolve_identity, api_server_cache: SessionIdentityCache):
    """Wrap `tools.py`'s `make_identity_resolver` output so a tool call from
    an api_server turn also resolves: `resolve_identity`'s own gateway-style
    lookup (session key -> `SessionIdentityCache` -> `get_session_metadata`
    -> a cron job) never finds an api_server `session_id` — it was never
    registered with the gateway's own `SessionStore` — so this only ever
    adds a fallback, never changes what a gateway-platform call resolves to.
    """

    def resolve(*, session_id: Optional[str] = None, job_name: Optional[str] = None, **kwargs: Any) -> ActingIdentity:
        try:
            return resolve_identity(session_id=session_id, job_name=job_name, **kwargs)
        except LookupError:
            person = api_server_cache.get(session_id) if session_id else None
            if person is not None:
                return person.identity
            raise

    return resolve
