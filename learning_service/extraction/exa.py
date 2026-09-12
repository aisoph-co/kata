"""Fourth grounding source (repo/issues/release notes/Exa, CI1): one
best-effort external citation for a concept whose local seeded sources
leave it thin (e.g. `sca-exemptions` — `issues.jsonl` says the change is
coming but not what the regulation actually requires).

Gated by `EXA_API_KEY`: unconfigured, `search` returns `None` before any
request is made, so ingestion never needs a key to run end-to-end against
the seeded Ferry sources, and the test suite never makes a network call.
"""

from __future__ import annotations

import os

import httpx

EXA_SEARCH_URL = "https://api.exa.ai/search"


class ExaClient:
    def __init__(self, api_key: str | None = None, timeout: float = 10.0) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("EXA_API_KEY", "")
        self._timeout = timeout

    async def search(self, query: str) -> dict[str, str] | None:
        if not self._api_key:
            return None
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                EXA_SEARCH_URL,
                headers={"x-api-key": self._api_key},
                json={"query": query, "numResults": 1},
            )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        top = results[0]
        return {"url": str(top.get("url", "")), "title": str(top.get("title", query))}
