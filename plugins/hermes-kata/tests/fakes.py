"""Lightweight stand-ins for the real Hermes plugin API surface, shaped to
match the calls this plugin makes (`ctx.register_tool`, `ctx.register_hook`,
`ctx.register_system_prompt_section`, `ctx.register_skill`,
`ctx.cron.jobs.create_job`/`.get_job`) and the `pre_gateway_dispatch` hook kwargs
(`event`, `gateway`, `session_store`) as documented in `hermes_cli/
plugins.py`'s `VALID_HOOKS`. Not the real Hermes — importing it isn't
possible outside a Hermes install — but a contract double these tests
assert against.

`FakeSessionStore`/`FakeGateway` mirror the real method names
(`gateway.session.SessionStore.set_session_metadata`/`get_session_metadata`/
`lookup_by_session_id`, `GatewayRunner._session_key_for_source`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional


class FakeCronJobs:
    """Stands in for `ctx.cron.jobs` — `create_job` keyed on `name`, and
    idempotent on it the same way the real one is documented to be: a
    second call with a name already on file overwrites that entry in place
    rather than appending a duplicate."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.calls: list[dict] = []

    def create_job(self, *, name: str, **kwargs: Any) -> dict:
        job = {"name": name, **kwargs}
        self.calls.append(job)
        self.jobs[name] = job
        return job

    def get_job(self, name: str) -> Optional[dict]:
        # Read side of the same store `create_job` writes — stands in for
        # the (unconfirmed against a live Hermes) `cron.jobs.get_job` read
        # API `tools.cron_job_recipient_lookup` calls, KATA-24 fix round 3.
        return self.jobs.get(name)


class FakeCron:
    def __init__(self) -> None:
        self.jobs = FakeCronJobs()


class FakePluginContext:
    def __init__(self) -> None:
        self.tools: dict[str, dict] = {}
        self.hooks: dict[str, list[Callable]] = {}
        self.system_prompt_sections: dict[str, dict] = {}
        self.skills: dict[str, Path] = {}
        self.cron = FakeCron()

    def register_tool(self, *, name, toolset, schema, handler, description="", **_):
        self.tools[name] = {
            "toolset": toolset,
            "schema": schema,
            "handler": handler,
            "description": description,
        }

    def register_hook(self, hook_name: str, callback: Callable):
        self.hooks.setdefault(hook_name, []).append(callback)

    def register_system_prompt_section(self, id, content, *, position="after_memory", max_chars=2000):
        self.system_prompt_sections[id] = {"content": content, "position": position, "max_chars": max_chars}

    def register_skill(
        self, name: str, path: Path, description: str = "", frontmatter: Optional[Mapping[str, Any]] = None,
    ):
        # Mirrors the real `ctx.register_skill(name, path, description="",
        # frontmatter=None)` (confirmed against `hermes_cli/plugins.py` on a
        # live Hermes install, KATA-17 deploy verification — it takes the
        # SKILL.md `Path` and calls `path.exists()` itself, raising
        # `FileNotFoundError` if missing; earlier versions of this fake
        # wrongly modeled it as taking the file's content, which let
        # `guardrails.register_socratic_debate_skill` ship a call that broke
        # against the real API). This fake keeps the bare name since every
        # test here only needs to see the id it was called with, not the
        # loader's own `<plugin.yaml name>:<name>` namespacing.
        if not path.exists():
            raise FileNotFoundError(f"SKILL.md not found at {path}")
        self.skills[name] = path


@dataclass
class FakeSource:
    platform: str
    user_id: str
    user_id_alt: Optional[str] = None


@dataclass
class FakeMessageEvent:
    # No `session_key` field — the real `MessageEvent` doesn't have one
    # either; it's derived by the gateway from `source` (see `FakeGateway`).
    source: FakeSource
    text: str = ""


class FakeGateway:
    def __init__(self) -> None:
        self.replies: list[tuple[FakeMessageEvent, str]] = []

    def send_reply(self, event: FakeMessageEvent, text: str) -> None:
        self.replies.append((event, text))

    def _session_key_for_source(self, source: FakeSource) -> str:
        # Stands in for `gateway/run.py`'s real derivation: stable per
        # (platform, user_id), good enough for these tests' purposes.
        return f"{source.platform}:{source.user_id}"


@dataclass
class FakeSessionEntry:
    session_key: str
    session_id: str
    metadata: dict


class FakeSessionStore:
    """Mirrors the real `gateway.session.SessionStore`:
    `set_session_metadata(session_key, key, value) -> bool`,
    `get_session_metadata(session_key, key, default=None)`, and
    `lookup_by_session_id(session_id) -> SessionEntry | None`.

    `link_session_id` is a test-only helper standing in for what a real
    session's creation does — associate a `session_id` with its
    `session_key` — so tests can exercise the id-differs-from-key path
    (e.g. a session reset).
    """

    def __init__(self) -> None:
        self._metadata: dict[str, dict[str, Any]] = {}
        self._session_id_to_key: dict[str, str] = {}

    def set_session_metadata(self, session_key: str, key: str, value: Any) -> bool:
        self._metadata.setdefault(session_key, {})[key] = value
        return True

    def get_session_metadata(self, session_key: str, key: str, default: Any = None) -> Any:
        return self._metadata.get(session_key, {}).get(key, default)

    def link_session_id(self, session_id: str, session_key: str) -> None:
        self._session_id_to_key[session_id] = session_key

    def lookup_by_session_id(self, session_id: str) -> Optional[FakeSessionEntry]:
        session_key = self._session_id_to_key.get(session_id)
        if session_key is None:
            return None
        return FakeSessionEntry(
            session_key=session_key, session_id=session_id, metadata=dict(self._metadata.get(session_key, {}))
        )


class FakeLearningServiceClient:
    """A `LearningServiceClient` double implementing its public contract
    directly (`resolve_identity` -> dict | None, `is_manager` -> bool,
    `request` -> canned value or a raised error) — no network."""

    def __init__(self, *, person: Optional[dict] = None, manager: bool = False) -> None:
        self._person = person
        self._manager = manager
        self.responses: dict[tuple[str, str], Any] = {}
        self.errors: dict[tuple[str, str], Exception] = {}
        self.calls: list[dict] = []

    def set_response(self, method: str, path: str, value: Any) -> None:
        self.responses[(method, path)] = value

    def set_error(self, method: str, path: str, error: Exception) -> None:
        self.errors[(method, path)] = error

    def request(self, method, path, *, identity=None, params=None, json_body=None):
        self.calls.append(
            {"method": method, "path": path, "identity": identity, "params": params, "json_body": json_body}
        )
        key = (method, path)
        if key in self.errors:
            raise self.errors[key]
        return self.responses.get(key)

    def resolve_identity(self, platform, external_id, alt_id=None):
        self.calls.append({"method": "resolve_identity", "platform": platform, "external_id": external_id})
        return self._person

    def is_manager(self, identity):
        return self._manager
