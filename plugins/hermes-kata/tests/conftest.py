"""Shared fakes for hermes-kata tests: a stand-in PluginContext, gateway,
session store, and message event — no real Hermes install needed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class FakeSource:
    platform: str
    user_id: str
    user_id_alt: str | None = None


@dataclass
class FakeEvent:
    source: FakeSource
    session_key: str


class FakeGateway:
    def __init__(self):
        self.replies: list[tuple[FakeEvent, str]] = []

    def send_reply(self, event, message):
        self.replies.append((event, message))


class FakeSessionStore:
    def __init__(self):
        self._data: dict[str, dict[str, Any]] = {}

    def set(self, session_key, key, value):
        self._data.setdefault(session_key, {})[key] = value

    def get(self, session_key, key=None, default=None):
        bucket = self._data.get(session_key, {})
        if key is None:
            return bucket
        return bucket.get(key, default)


class FakePluginContext:
    """Mirrors the real Hermes `PluginContext` surface this plugin actually
    uses — `register_tool`, `register_hook`, `register_system_prompt_section`
    — and nothing else. There is no `register_pre_gateway_dispatch`
    shortcut on the real API, so there isn't one here either: a plugin that
    calls a nonexistent method fails this fake with `AttributeError`
    instead of passing a suite that never exercised real registration.
    """

    def __init__(self):
        self.tools: dict[str, dict[str, Any]] = {}
        self.hooks: dict[str, list[Callable]] = {}
        self.prompt_sections: dict[str, Any] = {}

    def register_tool(self, name, toolset, schema, handler, description):
        self.tools[name] = {
            "toolset": toolset,
            "schema": schema,
            "handler": handler,
            "description": description,
        }

    def register_hook(self, hook_name, callback):
        self.hooks.setdefault(hook_name, []).append(callback)

    def register_system_prompt_section(self, name, callback, position="after_memory", **kwargs):
        self.prompt_sections[name] = {"callback": callback, "position": position}


class FakeLLMClient:
    """Records every call so identity tests can assert zero were made."""

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("mock LLM client should never be called for an unresolved identity")


class FakeIdentityClient:
    def __init__(self, known: dict[tuple[str, str], dict[str, Any]] | None = None):
        self.known = known or {}
        self.calls: list[tuple[str, str, str | None]] = []

    def resolve_identity(self, platform, external_id, alt_id=None):
        self.calls.append((platform, external_id, alt_id))
        return self.known.get((platform, external_id))
