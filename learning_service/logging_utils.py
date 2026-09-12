"""Loggers for request access lines and failed-identity warnings.

`serve.py` runs uvicorn with `log_level="info"`, but uvicorn's own logging
setup (`uvicorn.config.LOGGING_CONFIG`) only configures the `uvicorn`,
`uvicorn.error` and `uvicorn.access` logger names — it never touches the
root logger, which Python defaults to WARNING. A logger created the usual
way (`logging.getLogger(__name__)`) would inherit that WARNING default and
have its INFO records silently dropped once this runs as a deployed
process, even though the exact same code appears to work under pytest.

So these two loggers get an explicit level and their own handler here,
independent of uvicorn's config. `propagate` is left at its default
(`True`) so `caplog` in tests — which captures via a handler on the root
logger — still sees every record; the module-level handler below is what
makes the same record visible on stdout in production.
"""

from __future__ import annotations

import logging
import sys

request_logger = logging.getLogger("learning_service.request")
auth_logger = logging.getLogger("learning_service.auth")

for _logger in (request_logger, auth_logger):
    if not _logger.handlers:
        _handler = logging.StreamHandler(sys.stdout)
        _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)


def log_unknown_identity(*, path: str, platform: str, external_id: str, alt_id: str | None) -> None:
    """One WARNING format for every `403 unknown_identity` rejection site.

    This is the only record of the platform/external_id/alt_id that failed
    to resolve — never log the bearer token or any other request field here.
    """
    auth_logger.warning(
        "unknown_identity path=%s platform=%s external_id=%s alt_id=%s",
        path,
        platform,
        external_id,
        alt_id,
    )
