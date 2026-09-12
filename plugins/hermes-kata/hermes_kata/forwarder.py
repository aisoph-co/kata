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

Two optional hooks, both consulted only for `submit_review` (wired in by
`catalog.py`, issue G1): `is_quiz_item` sends the resolved answer's identity
with `platform="slack_thread"` when the item is one of today's tracked
team-quiz items (`quiz.TeamQuizItemRegistry`) — already a valid enum value
in the frozen contract, so the core's own `source` fallback writes `source =
slack_thread` for it with no contract change; `on_review` feeds every
*accepted* response back to `reveal.record_submit_review` so the team-quiz
tally (and, for a correct answer, `CorrectAnswerers`) stays current.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

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


def make_forwarder(
    client,
    method: str,
    path: str,
    *,
    is_quiz_item: Optional[Callable[[Any], bool]] = None,
    on_review: Optional[Callable[..., None]] = None,
) -> Callable[..., Any]:
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

        acting_person = person
        if person is not None and is_quiz_item is not None and is_quiz_item(call_kwargs.get("item_id")):
            acting_person = {**person, "platform": "slack_thread"}

        response = client.request(
            method,
            resolved_path,
            identity=_identity_header(acting_person) if acting_person else None,
            payload=call_kwargs,
        )
        if response.error_code is not None:
            return {"error": _ERROR_MESSAGES.get(response.error_code, _DEFAULT_ERROR_MESSAGE)}

        if on_review is not None:
            item_id = call_kwargs.get("item_id")
            item_response = call_kwargs.get("response")
            if item_id is not None and isinstance(item_response, dict):
                on_review(item_id, item_response, person_name=person.get("display_name") if person else None)

        return response.data

    return handler
