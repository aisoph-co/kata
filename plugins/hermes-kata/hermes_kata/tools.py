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
    Populated by `digest.py` at job-creation time for a job this plugin
    itself planned, and from `KATA_JOB_IDENTITIES` (`job_identities_from_env`,
    below) at plugin registration for a job created some other way — this
    in-process registry never sees a `hermes cron create` run directly
    against Hermes (e.g. a demo/ad hoc job made outside `/kata-sync-digests`),
    so that job's binding has to come from durable config instead
    (KATA-24 fix round 2).
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


def job_identities_from_env(raw: Optional[str]) -> dict[str, ActingIdentity]:
    """Parse `KATA_JOB_IDENTITIES` (deploy config) into `job_name ->
    ActingIdentity` bindings — durable metadata for a cron job this plugin
    never created itself, so `digest.py` never had a chance to register it
    (KATA-24 fix round 2: a job created directly against Hermes's cron API,
    not by `/kata-sync-digests`). Loaded once at `register(ctx)`, before any
    `/kata-sync-digests` run, so a fresh deploy can already resolve a job
    that config names.

    `raw` is a JSON object, `{"<job-name>": "<platform>:<external_id>", ...}`
    — the same `platform:external_id` shape `digest.DigestRecipient.identity`
    already uses. Unset/blank is a no-op, same convention as
    `LEARNING_SERVICE_SRC`/`KATA_TOOLS_JSON` elsewhere in this plugin. A
    value that isn't valid JSON, isn't an object, or has an entry that
    doesn't parse to a non-empty platform/external_id is skipped — one bad
    or malformed entry must never keep every other binding (or plugin
    registration itself) from loading."""
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    identities: dict[str, ActingIdentity] = {}
    for name, value in parsed.items():
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        platform, sep, external_id = value.partition(":")
        if sep and platform and external_id:
            identities[name] = ActingIdentity(platform=platform, external_id=external_id)
    return identities


def make_identity_resolver(
    session_cache: SessionIdentityCache,
    job_identities: JobIdentityRegistry,
    store_handle: SessionStoreHandle,
    *,
    job_recipient_lookup: Optional[Callable[[str], Optional[Mapping[str, str]]]] = None,
) -> Callable[..., ActingIdentity]:
    """Resolution order for a tool call (spec §1/§2): `session_id` ->
    `lookup_by_session_id` -> session key -> plugin cache ->
    `session_store.get_session_metadata` (a session that outlived the plugin
    cache, e.g. a reload) -> the cron job it was scheduled by, from
    `job_identities` (this plugin's own registrations plus `KATA_JOB_
    IDENTITIES`) -> `job_recipient_lookup`, the cron job's own durably
    recorded recipient (KATA-24 fix round 3: a job neither this plugin nor
    deploy config ever registered — e.g. one made directly against Hermes's
    cron API — still carries its own `recipient` there, so this is a
    fallback, not a substitute, for `job_identities`; an env/registry entry
    always wins if both exist) -> raise. A session reset changes
    `session_id` but keeps `session_key`, so it still resolves via the same
    cache/metadata entry. A resolved `job_recipient_lookup` hit is also
    cached into `job_identities`, so only the first tool call on a given job
    pays for the lookup.
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
        if job_recipient_lookup is not None and job_name:
            recipient = job_recipient_lookup(job_name)
            if recipient is not None:
                identity = ActingIdentity(platform=recipient["platform"], external_id=recipient["external_id"])
                job_identities.set(job_name, identity)
                return identity
        raise LookupError(
            "hermes-kata: no bound identity for this tool call — "
            "neither an active session nor a known cron job"
        )

    return resolve


def cron_job_recipient_lookup(cron: Any) -> Optional[Callable[[str], Optional[Mapping[str, str]]]]:
    """Best-effort `job_recipient_lookup` (`make_identity_resolver`, above)
    over `ctx.cron.jobs`'s own durable job record — the "resolve it from
    durable job metadata" fallback (KATA-24 fix round 3) for a job this
    plugin never created and deploy config never named. `cron.jobs.
    create_job`'s persisted shape carries a `recipient` (`digest.py`); this
    assumes a symmetric read, `cron.jobs.get_job(name) -> Mapping | None`,
    unconfirmed against a live Hermes (unlike `create_job`, no test here
    exercised the read side before this fix) — so every step is `getattr`-
    guarded and every call wrapped, exactly like `register()`'s own
    `getattr(ctx, "cron", None)`: a `cron`/`.jobs` that doesn't expose
    `get_job`, or a `get_job` that raises or returns something unexpected,
    degrades to `None` (the resolver's caller then falls through to its own
    `LookupError`) rather than taking the whole tool call down.
    """
    jobs = getattr(cron, "jobs", None) if cron is not None else None
    get_job = getattr(jobs, "get_job", None) if jobs is not None else None
    if get_job is None:
        return None

    def lookup(job_name: str) -> Optional[Mapping[str, str]]:
        try:
            job = get_job(job_name)
        except Exception:  # noqa: BLE001 - best-effort, spec KATA-31
            return None
        recipient = job.get("recipient") if isinstance(job, Mapping) else getattr(job, "recipient", None)
        if not isinstance(recipient, Mapping):
            return None
        platform, external_id = recipient.get("platform"), recipient.get("external_id")
        if not platform or not external_id:
            return None
        return {"platform": platform, "external_id": external_id}

    return lookup


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
