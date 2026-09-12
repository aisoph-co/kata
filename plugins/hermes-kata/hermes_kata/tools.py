"""Job 2 (adapter-contract): forward tools.

Loads `tools.json` — the single source of truth — and registers exactly what
it lists, no more, no less (spec §1: "Adding a tool means editing `tools.json`
once and none of the adapters" is only true if the adapter is a loader, not a
transcription).
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from .client import ActingIdentity, LearningServiceClient, LearningServiceError
from .identity import (
    SESSION_METADATA_KEY,
    SessionIdentityCache,
    SessionStoreHandle,
    person_from_metadata,
    session_key_for_session_id,
)

TOOLSET = "learning"

_PATH_PARAM = re.compile(r"\{(\w+)\}")

# Core error codes that must never reach a learner as a raw 403/JSON dump
# (spec §1, "make_forwarder ... maps the core's error codes").
_FRIENDLY_ERRORS = {
    "outside_subtree": "that's not something I can show you",
    "not_a_manager": "that's not something I can show you",
}


def _default_tools_json_path() -> Path:
    override = os.environ.get("KATA_TOOLS_JSON")
    if override:
        return Path(override)
    # `tools.json` lives with the learning service in `aisoph-co/agency-v1`,
    # not this repo. Resolve it the same way the rest of build-day resolves
    # that repo: `LEARNING_SERVICE_SRC`, default a sibling `agency-v1/`
    # checkout — how `multica repo checkout` lays out this workspace.
    learning_service_src = Path(
        os.environ.get("LEARNING_SERVICE_SRC")
        or Path(__file__).resolve().parents[3].parent / "agency-v1"
    )
    return learning_service_src / "learning_service" / "tools.json"


def load_catalog(path: Optional[Path] = None) -> list[dict]:
    path = path or _default_tools_json_path()
    return json.loads(path.read_text(encoding="utf-8"))["tools"]


def _split_path_params(path_template: str, args: Mapping[str, Any]) -> tuple[str, dict]:
    """Substitute `{id}`-style path params from `args`; return the resolved
    path plus whatever's left over for the body/query string (spec §1)."""
    remaining = dict(args)

    def _sub(match: "re.Match[str]") -> str:
        return str(remaining.pop(match.group(1)))

    return _PATH_PARAM.sub(_sub, path_template), remaining


class JobIdentityRegistry:
    """Maps a cron job's name to the recipient's identity, so a tool call made
    from a cron-triggered turn (no `MessageEvent`, no `pre_gateway_dispatch`)
    can still resolve identity from "the job's own recorded platform/
    external-id instead of failing closed on a missing header" (spec §1).
    Empty until a digest-scheduling issue populates it — this plugin build
    ships no cron jobs (spec §6, tracked separately).
    """

    def __init__(self) -> None:
        self._data: dict[str, ActingIdentity] = {}
        self._lock = threading.Lock()

    def set(self, job_name: str, identity: ActingIdentity) -> None:
        with self._lock:
            self._data[job_name] = identity

    def get(self, job_name: Optional[str]) -> Optional[ActingIdentity]:
        if not job_name:
            return None
        with self._lock:
            return self._data.get(job_name)


def make_identity_resolver(
    session_cache: SessionIdentityCache, job_identities: JobIdentityRegistry, store_handle: SessionStoreHandle
) -> Callable[..., ActingIdentity]:
    """Resolution order for a tool call (spec §1/§2): `session_id` ->
    `lookup_by_session_id` -> session key -> plugin cache ->
    `session_store.get_session_metadata` (a session that outlived the plugin
    cache, e.g. a reload) -> the cron job it was scheduled by -> raise. A
    session reset changes `session_id` but keeps `session_key`, so it still
    resolves via the same cache/metadata entry.
    """

    def resolve(*, session_id: Optional[str] = None, job_name: Optional[str] = None, **_: Any) -> ActingIdentity:
        session_key = session_key_for_session_id(store_handle, session_id)
        if session_key is not None:
            person = session_cache.get(session_key)
            if person is not None:
                return person.identity
            store = store_handle.store
            getter = getattr(store, "get_session_metadata", None) if store is not None else None
            if getter is not None:
                person = person_from_metadata(getter(session_key, SESSION_METADATA_KEY, None))
                if person is not None:
                    return person.identity
        identity = job_identities.get(job_name)
        if identity is not None:
            return identity
        raise LookupError(
            "hermes-kata: no bound identity for this tool call — "
            "neither an active session nor a known cron job"
        )

    return resolve


def make_forwarder(
    client: LearningServiceClient,
    method: str,
    path_template: str,
    *,
    resolve_identity: Callable[..., ActingIdentity],
) -> Callable[..., str]:
    """One handler per `tools.json` endpoint (spec §1). Returns a JSON
    string — the only shape `tools/registry.py::dispatch` accepts from a
    plugin tool handler (`_normalize_handler_result`)."""

    def handler(args: Mapping[str, Any], *, session_id: Optional[str] = None, **kwargs: Any) -> str:
        identity = resolve_identity(session_id=session_id, job_name=kwargs.get("job_name"))
        resolved_path, remaining = _split_path_params(path_template, args)
        try:
            if method in ("GET", "DELETE"):
                result = client.request(method, resolved_path, identity=identity, params=remaining or None)
            else:
                result = client.request(method, resolved_path, identity=identity, json_body=remaining or None)
        except LearningServiceError as exc:
            friendly = _FRIENDLY_ERRORS.get(exc.code)
            if friendly is None:
                raise
            return json.dumps({"error": friendly})
        # `tools/registry.py::dispatch` pipes a handler's return straight into
        # `_normalize_handler_result`, which accepts only `str` (or the
        # `_multimodal` envelope) — a bare dict/list/None is logged as an
        # "unsupported result type" and replaced with an error string instead
        # of reaching the model. `client.request` returns parsed JSON, so it
        # must be re-serialized here before crossing back into Hermes.
        return json.dumps(result)

    return handler


def register_tools(
    ctx: Any,
    client: LearningServiceClient,
    *,
    resolve_identity: Callable[..., ActingIdentity],
    tools_json_path: Optional[Path] = None,
) -> list[str]:
    """Register every `tools.json` entry under the `learning` toolset.
    Returns the registered tool names (used by the contract test, spec §1)."""
    registered = []
    for tool in load_catalog(tools_json_path):
        handler = make_forwarder(
            client,
            tool["endpoint"]["method"],
            tool["endpoint"]["path"],
            resolve_identity=resolve_identity,
        )
        ctx.register_tool(
            name=tool["name"],
            toolset=TOOLSET,
            schema=tool["parameters"],
            handler=handler,
            description=tool.get("description", ""),
        )
        registered.append(tool["name"])
    return registered
