"""Builds one tool handler per learning-service endpoint (spec §1).

Each handler:
- reads the acting identity `pre_gateway_dispatch` (see `identity.py`)
  stashed on `session_store` for this session; a call reaching this path
  outside a bound turn (a cron digest job, spec §6) resolves identity from
  the job's own recorded platform/external-id instead of failing closed on
  a missing session value;
- substitutes `{id}`-style path parameters from the tool's own arguments
  and sends the remainder as the JSON body (POST/DELETE) or query string
  (GET) — handled by `client.request`;
- sends the bearer token + `X-Acting-Identity` header (via `client`);
- maps the core's error codes to short, learner-facing text — never a raw
  403/JSON dump.
"""
from __future__ import annotations

import re
from typing import Any, Callable

_PATH_PARAM = re.compile(r"\{(\w+)\}")

_ERROR_MESSAGES = {
    "outside_subtree": "that's not something I can show you",
    "not_a_manager": "that's not something I can show you",
}
_DEFAULT_ERROR_MESSAGE = "Sorry, that didn't work — try again in a moment."


def _identity_header(person: dict[str, Any]) -> str:
    header = f"{person['platform']}:{person['external_id']}"
    if person.get("alt_id"):
        header += f";alt={person['alt_id']}"
    return header


def make_forwarder(client, method: str, path: str) -> Callable[..., Any]:
    def handler(
        session_store,
        session_key: str,
        job_identity: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        person = session_store.get(session_key, "kata_person")
        if person is None:
            if job_identity is None:
                raise RuntimeError(
                    f"no bound identity for session {session_key!r} and no "
                    "job_identity given"
                )
            person = client.resolve_identity(**job_identity)

        call_kwargs = dict(kwargs)
        resolved_path = path
        for param in _PATH_PARAM.findall(path):
            if param not in call_kwargs:
                raise KeyError(
                    f"missing path parameter {param!r} for {method} {path}"
                )
            resolved_path = resolved_path.replace(
                f"{{{param}}}", str(call_kwargs.pop(param))
            )

        response = client.request(
            method,
            resolved_path,
            identity=_identity_header(person) if person else None,
            payload=call_kwargs,
        )
        if response.error_code is not None:
            return {"error": _ERROR_MESSAGES.get(response.error_code, _DEFAULT_ERROR_MESSAGE)}
        return response.data

    return handler
