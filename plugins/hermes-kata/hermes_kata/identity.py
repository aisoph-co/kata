"""Job 1 (adapter-contract): bind identity.

`pre_gateway_dispatch` hook (spec §2). Fires once per inbound `MessageEvent`,
before auth/pairing and before the agent turn starts — the only hook that can
refuse a message before Hermes does anything else with it (spec "Decisions",
"Identity-binding hook").
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Optional

from .client import ActingIdentity, LearningServiceClient

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
