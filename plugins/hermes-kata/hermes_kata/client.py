"""HTTP client for the learning service core.

The one place in this plugin that knows the service token and the
`X-Acting-Identity` header shape (docs/adapter-contract.md job 2; spec
"Decisions" table, "Identity assertion header").
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import httpx


@dataclass(frozen=True)
class ActingIdentity:
    """A `(platform, external_id[, alt_id])` triple — never accepted from
    model output, only from a trusted transport context (adapter-contract
    job 1)."""

    platform: str
    external_id: str
    alt_id: Optional[str] = None

    def header_value(self) -> str:
        value = f"{self.platform}:{self.external_id}"
        if self.alt_id:
            value += f";alt={self.alt_id}"
        return value


class LearningServiceError(Exception):
    """A core error response: `{"detail": {"code": ..., "message": ...}}`
    (learning/openapi.yaml `ErrorResponse`)."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message


class LearningServiceClient:
    """Thin wrapper over the core's HTTP API. Every call carries the service
    token; calls made on behalf of a learner also carry the bound acting
    identity."""

    def __init__(self, base_url: str, token: str, *, http: Optional[httpx.Client] = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._http = http or httpx.Client(timeout=10.0)

    @classmethod
    def from_env(cls) -> "LearningServiceClient":
        return cls(os.environ["LEARNING_SERVICE_URL"], os.environ["LEARNING_SERVICE_TOKEN"])

    def request(
        self,
        method: str,
        path: str,
        *,
        identity: Optional[ActingIdentity] = None,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self._token}"}
        if identity is not None:
            headers["X-Acting-Identity"] = identity.header_value()
        response = self._http.request(
            method,
            f"{self._base_url}{path}",
            headers=headers,
            params=params,
            json=json_body,
        )
        if response.status_code >= 400:
            detail: Mapping[str, Any] = {}
            try:
                detail = response.json().get("detail", {}) or {}
            except ValueError:
                pass
            raise LearningServiceError(
                response.status_code,
                str(detail.get("code", "unknown_error")),
                str(detail.get("message", response.text)),
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def resolve_identity(
        self, platform: str, external_id: str, alt_id: Optional[str] = None
    ) -> Optional[dict]:
        """`POST /identities/resolve`. Returns `None` on `unknown_identity`
        (403) — refuse, never auto-create (core spec invariant, spec §2)."""
        body: dict = {"platform": platform, "external_id": external_id}
        if alt_id:
            body["alt_id"] = alt_id
        try:
            return self.request("POST", "/identities/resolve", json_body=body)
        except LearningServiceError as exc:
            if exc.code == "unknown_identity":
                return None
            raise

    def is_manager(self, identity: ActingIdentity) -> bool:
        """`is_manager` = whether `/team/overview` 403s for this identity
        (spec §2, "Identity hook")."""
        try:
            self.request("GET", "/team/overview", identity=identity)
            return True
        except LearningServiceError as exc:
            if exc.code == "not_a_manager":
                return False
            raise
