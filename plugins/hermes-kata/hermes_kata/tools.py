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


def _parse_platform_external_id(value: str) -> Optional[tuple[str, str]]:
    """`"<platform>:<external_id>"` -> `(platform, external_id)`, or `None`
    if it doesn't parse to two non-empty halves. The one string shape every
    env-driven identity override in this module accepts, factored out so
    `job_identities_from_env` and `default_acting_identity_from_env` agree
    on it exactly."""
    platform, sep, external_id = value.partition(":")
    if sep and platform and external_id:
        return platform, external_id
    return None


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
    registration itself) from loading.

    Keyed by job *name* — since fix round 4, this only ever matches
    `job_identities.get(job_name)` in `make_identity_resolver`, which is
    always `None` in production (`cron_job_id_from_session_id`'s docstring);
    an override that needs to actually take effect on a live job has to be
    keyed by that job's *id* instead (the same map works for either — the
    registry doesn't care which shape of string named the entry)."""
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
        pair = _parse_platform_external_id(value)
        if pair is not None:
            identities[name] = ActingIdentity(platform=pair[0], external_id=pair[1])
    return identities


def default_acting_identity_from_env(raw: Optional[str]) -> Optional[ActingIdentity]:
    """Parse `KATA_DEFAULT_ACTING_IDENTITY` (deploy config, KATA-24 fix
    round 5): the identity a *group* cron job's tool calls act as, for when
    that job's own `deliver` names the channel it posts into rather than a
    person — `_is_slack_group_recipient`, `make_identity_resolver`, below.

    A due-rep/DM digest job's `deliver` is the recipient's own id, which
    already doubles correctly as their acting identity (fix round 4) — nothing
    here changes that path. A team-quiz/teach-back/demo-quiz job's `deliver`
    is a Slack channel (`kata-demo-quiz-B-C0C10B1KHHP` -> `slack:
    C0C10B1KHHP`), and no channel is ever a person the learning service can
    act on behalf of — every such job hit `unknown_identity: no person
    matches this identity` once fix round 4 correctly started resolving
    *a* identity for it, just the channel's, not a person's. This names a
    real, already-seeded learning-service person (e.g. `slack:U0C03BWUVEE`,
    Ferry's Quinn Halloran, the tech lead/operator) to act as for every such
    job instead, without needing a per-job override.

    `raw` is a single `"platform:external_id"` string, the same shape one
    `KATA_JOB_IDENTITIES` value uses. Unset/blank/malformed is `None` — a
    no-op, same convention as every other env-driven default in this
    plugin; never raises on a bad value."""
    if not raw or not raw.strip():
        return None
    pair = _parse_platform_external_id(raw.strip())
    if pair is None:
        return None
    return ActingIdentity(platform=pair[0], external_id=pair[1])


# Slack's own conversation-id convention: `C…` public channel, `G…`
# private channel/group — a delivery target, never itself a person. `U…`/
# `D…` (user / DM channel) are individual, and correctly resolve as the
# recipient's own identity (fix round 4) — this is what tells a group cron
# job's `deliver` apart from a DM one's (KATA-24 fix round 5).
_SLACK_GROUP_ID_PREFIXES = ("C", "G")


def _is_slack_group_recipient(recipient: Mapping[str, str]) -> bool:
    return recipient.get("platform") == "slack" and recipient.get("external_id", "").startswith(
        _SLACK_GROUP_ID_PREFIXES
    )



# `cron/scheduler.py` builds a cron-triggered turn's session id as
# `f"cron_{job_id}_{timestamp:%Y%m%d_%H%M%S}"` (confirmed against a live
# `hermes-day`, 2026-09-12: every cron turn's `agent.log` line carries
# `session=cron_<job id>_<timestamp>`) — the same prefix Hermes's own
# `hermes_state_portability.py` relies on (`f"cron_{job_id}_"`), so this is a
# supported convention, not an incidental string we're scraping. `job_id` is
# the scheduler's 12-hex-char id (`cron/jobs.py`'s `uuid.uuid4().hex[:12]`),
# but matched loosely here in case that width ever changes upstream.
_CRON_SESSION_ID = re.compile(r"^cron_([0-9a-f]+)_\d{8}_\d{6}$")


def cron_job_id_from_session_id(session_id: Optional[str]) -> Optional[str]:
    """Recover a cron job's own id from the session id a cron-triggered turn
    actually carries (KATA-24 fix round 4). Rounds 2/3 both keyed their
    fallback off `job_name`, passed into `make_forwarder`'s handler via
    `kwargs.get("job_name")` — but Hermes's tool dispatch
    (`model_tools.py`'s `dispatch_kwargs`, confirmed against the public
    `hermes-agent` source) only ever forwards `task_id`/`session_id` to a
    plugin tool handler, never `job_name`. That made every prior fix
    structurally unreachable: `job_name` is `None` at the real call site on
    every cron run, group-chat or DM alike (confirmed live against
    `hermes-day`'s `agent.log`: every learning-tool call from a cron turn
    raises "no bound identity", regardless of job shape). `session_id` is
    the one identifier that's actually delivered, so this is the fallback
    that can actually fire.
    """
    if not session_id:
        return None
    match = _CRON_SESSION_ID.match(session_id)
    return match.group(1) if match else None


def make_identity_resolver(
    session_cache: SessionIdentityCache,
    job_identities: JobIdentityRegistry,
    store_handle: SessionStoreHandle,
    *,
    job_deliver_lookup: Optional[Callable[[str], Optional[Mapping[str, str]]]] = None,
    default_acting_identity: Optional[ActingIdentity] = None,
) -> Callable[..., ActingIdentity]:
    """Resolution order for a tool call (spec §1/§2): `session_id` ->
    `lookup_by_session_id` -> session key -> plugin cache ->
    `session_store.get_session_metadata` (a session that outlived the plugin
    cache, e.g. a reload) -> the cron job it was scheduled by, from
    `job_identities` (this plugin's own registrations plus `KATA_JOB_
    IDENTITIES`, keyed by job *name*) -> the same registry keyed by the job
    *id* recovered from `session_id` (`cron_job_id_from_session_id`) ->
    `job_deliver_lookup` against that id, the cron job's own durably
    recorded `deliver` target (KATA-24 fix round 4 — a job neither this
    plugin nor deploy config ever registered still carries its own
    `deliver` string there) -> raise. A session reset changes `session_id`
    but keeps `session_key`, so it still resolves via the same
    cache/metadata entry. A resolved `job_deliver_lookup` hit is cached
    into `job_identities` (keyed by job id) so only the first tool call on
    a given job pays for the lookup.

    KATA-24 fix round 5: when the `job_deliver_lookup` hit names a Slack
    channel/group rather than a person (`_is_slack_group_recipient`) —
    every team-quiz/teach-back/demo-quiz job, whose `deliver` is where it
    posts, not who it acts as — `default_acting_identity` is used instead,
    if configured (`KATA_DEFAULT_ACTING_IDENTITY`). A DM/due-rep job's
    `deliver` is the recipient's own id, never channel-shaped, so it's
    unaffected and keeps resolving exactly as fix round 4 left it. With no
    `default_acting_identity` configured, behavior is unchanged from round
    4 (the channel's own "identity" is used, same as before this round).
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
        job_id = cron_job_id_from_session_id(session_id)
        identity = job_identities.get(job_id)
        if identity is not None:
            return identity
        if job_deliver_lookup is not None:
            for key in (job_name, job_id):
                if not key:
                    continue
                recipient = job_deliver_lookup(key)
                if recipient is not None:
                    if default_acting_identity is not None and _is_slack_group_recipient(recipient):
                        identity = default_acting_identity
                    else:
                        identity = ActingIdentity(platform=recipient["platform"], external_id=recipient["external_id"])
                    job_identities.set(key, identity)
                    return identity
        raise LookupError(
            "hermes-kata: no bound identity for this tool call — "
            "neither an active session nor a known cron job"
        )

    return resolve


def cron_job_deliver_lookup(
    get_job: Optional[Callable[[str], Any]] = None,
) -> Callable[[str], Optional[Mapping[str, str]]]:
    """`job_deliver_lookup` (`make_identity_resolver`, above): best-effort
    `job_id -> {"platform", "external_id"}` over a cron job's own persisted
    `deliver` string (KATA-24 fix round 4).

    Round 3 assumed a `ctx.cron.jobs.get_job` facade and a `recipient` dict
    on the job record. Neither exists: `PluginContext`
    (`hermes-agent`'s `hermes_cli/plugins.py`) has no `.cron` attribute at
    all — confirmed against the public upstream source — so that fallback
    was dead code regardless of the `get_job` signature question it was
    flagged with. `cron.jobs.create_job`'s real persisted shape only ever
    writes `deliver`, a plain `"platform:external_id"` string
    (`cron/jobs.py`), never a `recipient` mapping.

    This plugin loads in-process with Hermes (`__init__.py`'s own
    docstring: the loader `exec`s this file, it doesn't subprocess it), so
    it can read the job store directly — `import cron.jobs` — instead of
    going through `ctx`. `get_job` defaults to that module's `get_job(job_id)`
    (looked up by id this time, not name — matches the real signature),
    lazily imported so a test double can inject a fake via the `get_job`
    param and an environment without `cron.jobs` on `sys.path` degrades to
    `None` rather than raising.
    """

    def _default_get_job(job_id: str) -> Optional[Mapping[str, Any]]:
        from cron.jobs import get_job as _get_job  # in-process import; see above

        return _get_job(job_id)

    resolver = get_job or _default_get_job

    def lookup(job_id: str) -> Optional[Mapping[str, str]]:
        try:
            job = resolver(job_id)
        except Exception:  # noqa: BLE001 - best-effort, spec KATA-31
            return None
        deliver = job.get("deliver") if isinstance(job, Mapping) else getattr(job, "deliver", None)
        if not isinstance(deliver, str):
            return None
        platform, sep, external_id = deliver.partition(":")
        if not sep or not platform or not external_id:
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
