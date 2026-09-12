"""`pre_gateway_dispatch` identity-binding hook (spec §2).

Fires once per inbound message, before the agent turn starts and before any
tool call — the only hook that can refuse a message before Hermes does
anything else with it. An unknown identity is refused here, through the
gateway's own reply path, and never reaches the model.
"""
from __future__ import annotations

from typing import Any, Protocol

UNKNOWN_IDENTITY_MESSAGE = (
    "You're not set up as a Kata learner yet — ask your team admin for an invite."
)


class IdentityClient(Protocol):
    def resolve_identity(
        self, platform: str, external_id: str, alt_id: str | None = None
    ) -> dict[str, Any] | None: ...


def bind_identity(event, gateway, session_store, client: IdentityClient) -> dict[str, Any]:
    platform = event.source.platform
    external_id = event.source.user_id
    alt_id = getattr(event.source, "user_id_alt", None)

    # Resolution order (exact match, then alt_id, else unknown) lives in
    # `POST /identities/resolve` itself — the hook does not reimplement it.
    person = client.resolve_identity(platform, external_id, alt_id)
    if person is None:
        gateway.send_reply(event, UNKNOWN_IDENTITY_MESSAGE)
        return {"action": "skip", "reason": "unknown_identity"}

    # Enriched with the (platform, external_id[, alt_id]) triple so a tool
    # call later in the same turn can rebuild the X-Acting-Identity header
    # (see forwarder.py) without a second resolve call.
    bound = {**person, "platform": platform, "external_id": external_id, "alt_id": alt_id}
    # Re-resolved on every message, never cached across turns: a link/unlink
    # takes effect on the learner's very next message, not after a restart.
    session_store.set(event.session_key, "kata_person", bound)
    return {"action": "allow"}


def make_pre_gateway_dispatch(client: IdentityClient):
    """Bind `client` once; return the callback Hermes invokes per message."""

    def _hook(event, gateway, session_store):
        return bind_identity(event, gateway, session_store, client)

    return _hook
