"""Kata learning service.

Stage 0 core, built incrementally against the frozen contract (v1.2.1,
`contracts/openapi.yaml`): KATA-2 (this package) lands `identity`, `roster`
and `curriculum` — the two leaf packages nothing else in the core depends
on. `engine`, `grading`, `analytics`, `privacy` and the rest of `api` land
in the follow-up issue that depends on this one.

- ``GET /health`` and ``GET /health/db`` are unauthenticated.
- Every other route requires ``Authorization: Bearer $SERVICE_TOKEN`` (or
  ``$WEB_SERVICE_TOKEN``, the web app's own trusted-caller token) and an
  ``X-Acting-Identity: <platform>:<external_id>[;alt=<alt_id>]`` header.
"""

__version__ = "1.2.1"
