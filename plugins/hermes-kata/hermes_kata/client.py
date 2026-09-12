"""Thin HTTP client binding the plugin to the learning service's frozen
contract (core spec's API auth table): `Authorization: Bearer
$LEARNING_SERVICE_TOKEN` + `X-Acting-Identity`, JSON in and out.

Stdlib-only (no `requests`/`httpx` dependency) — this plugin's own test
suite talks to fakes, not this client, so the extra dependency would only
serve production traffic.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode


@dataclass
class ServiceResponse:
    status: int
    data: Any
    error_code: str | None = None


class LearningServiceClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.environ.get("LEARNING_SERVICE_URL", "")).rstrip("/")
        self.token = token or os.environ.get("LEARNING_SERVICE_TOKEN", "")

    def _headers(self, identity: str | None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        if identity:
            headers["X-Acting-Identity"] = identity
        return headers

    def request(
        self,
        method: str,
        path: str,
        identity: str | None,
        payload: dict[str, Any] | None = None,
    ) -> ServiceResponse:
        url = f"{self.base_url}{path}"
        payload = payload or {}
        body = None
        if method.upper() == "GET":
            if payload:
                url = f"{url}?{urlencode(payload)}"
        else:
            body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url, data=body, method=method.upper(), headers=self._headers(identity)
        )
        try:
            with urllib.request.urlopen(request) as resp:
                raw = resp.read().decode("utf-8")
                return ServiceResponse(status=resp.status, data=json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            return ServiceResponse(status=exc.code, data=data, error_code=data.get("error"))

    def resolve_identity(
        self, platform: str, external_id: str, alt_id: str | None = None
    ) -> dict[str, Any] | None:
        """`POST /identities/resolve` — exact match, then `alt_id`, else
        unknown. Never auto-creates (core spec invariant)."""
        payload: dict[str, Any] = {"platform": platform, "external_id": external_id}
        if alt_id:
            payload["alt_id"] = alt_id
        response = self.request("POST", "/identities/resolve", identity=None, payload=payload)
        if response.status == 403:
            return None
        return response.data
