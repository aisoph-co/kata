"""FastAPI app for the Kata learning service.

This module lands the app skeleton (health, auth, the acting-identity
contract) plus this issue's own routers: identity resolution/linking and
roster import (below), curriculum admin CRUD, topics, and the concept
graph (registered at the bottom, the same deferred-import pattern used
throughout so each router can depend on `require_service_token`,
`acting_identity`, `require_operator`, and `resolve_person_id` defined
here). Later Stage 0 issues (engine/grading/analytics/privacy, the rest of
`api`) extend this module with their own routers the same way.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service import __version__
from learning_service.db import get_session
from learning_service.engine.openrouter import LLMClient, OpenRouterClient
from learning_service.engine.sql_repository import SqlLearningRepository
from learning_service.engine.stub_grader import StubGraderClient
from learning_service.identity.schemas import (
    IdentityLinkRequest,
    IdentityOut,
    IdentityResolveRequest,
    LinkCodeResponse,
    PersonSummary,
)
from learning_service.identity.service import (
    IdentityAlreadyLinked,
    LinkCodeInvalid,
    consume_link_code,
    mint_link_code,
    resolve_identity,
)
from learning_service.logging_utils import log_unknown_identity, request_logger

app = FastAPI(title="Kata learning service", version=__version__)


@app.middleware("http")
async def _log_request(request: Request, call_next):
    # `/health` is Railway's liveness probe — it fires every few seconds and
    # would otherwise drown out the requests an operator actually cares
    # about, so it's the one path excluded here. Every other request logs
    # one INFO line: method, path, status code, and the acting identity
    # straight off the header (never parsed/validated here — this line must
    # still log something useful for requests that never reach the
    # `acting_identity` dependency).
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        if request.url.path != "/health":
            request_logger.info(
                "%s %s %s acting_identity=%s",
                request.method,
                request.url.path,
                status_code,
                request.headers.get("x-acting-identity", "-"),
            )


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@dataclass(frozen=True)
class ActingIdentity:
    platform: str
    external_id: str
    alt_id: str | None = None

    @classmethod
    def parse(cls, raw: str) -> "ActingIdentity":
        head, _, tail = raw.partition(";")
        platform, sep, external_id = head.partition(":")
        if not sep or not platform or not external_id:
            raise _error(422, "validation_error", "X-Acting-Identity must be <platform>:<external_id>")
        alt_id = None
        if tail.startswith("alt="):
            alt_id = tail[4:] or None
        return cls(platform=platform, external_id=external_id, alt_id=alt_id)


def require_service_token(request: Request) -> None:
    # Two trusted callers share this dependency: Hermes's `SERVICE_TOKEN`
    # and the web app's own `WEB_SERVICE_TOKEN`, checked identically — the
    # acting identity, not the token, says who is calling (e.g.
    # `X-Acting-Identity: web:<subject>`). Unset tokens are dropped, so a
    # misconfigured service still fails closed.
    valid_tokens = [t for t in (os.environ.get("SERVICE_TOKEN", ""), os.environ.get("WEB_SERVICE_TOKEN", "")) if t]
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not any(secrets.compare_digest(token, expected) for expected in valid_tokens):
        raise _error(401, "unauthorized", "missing or invalid service token")


def acting_identity(
    _: None = Depends(require_service_token),
    x_acting_identity: str | None = Header(default=None),
) -> ActingIdentity:
    if not x_acting_identity:
        raise _error(422, "validation_error", "X-Acting-Identity header is required")
    return ActingIdentity.parse(x_acting_identity)


async def require_operator(
    request: Request,
    identity: ActingIdentity = Depends(acting_identity),
    session: AsyncSession = Depends(get_session),
) -> None:
    person = await resolve_identity(
        session, platform=identity.platform, external_id=identity.external_id, alt_id=identity.alt_id
    )
    if person is None:
        log_unknown_identity(
            path=request.url.path,
            platform=identity.platform,
            external_id=identity.external_id,
            alt_id=identity.alt_id,
        )
        raise _error(403, "unknown_identity", "no person matches this identity")
    if not person.is_operator:
        raise _error(403, "not_operator", "operator access required")


async def resolve_person_id(
    request: Request,
    identity: ActingIdentity = Depends(acting_identity),
    session: AsyncSession = Depends(get_session),
) -> str:
    """Every `/me/*` route's acting person: the acting person is resolved
    before any handler runs; unknown identities are rejected (spec
    §Architecture, "Acting person")."""
    person = await resolve_identity(
        session, platform=identity.platform, external_id=identity.external_id, alt_id=identity.alt_id
    )
    if person is None:
        log_unknown_identity(
            path=request.url.path,
            platform=identity.platform,
            external_id=identity.external_id,
            alt_id=identity.alt_id,
        )
        raise _error(403, "unknown_identity", "no person matches this identity")
    return person.id


async def get_repository(session: AsyncSession = Depends(get_session)) -> AsyncIterator[SqlLearningRepository]:
    """Every `/me/*`, `/team/*`, and `/admin/replay` route's engine state
    (`review`, `card_state`, `concept_state`, curriculum, focus): one
    `SqlLearningRepository` per request, hydrated from the same session
    `resolve_person_id` already resolves identities through, so engine
    state and roster/identity state are always the same transaction.
    """
    repo = SqlLearningRepository(session)
    await repo.load()
    yield repo


def _build_llm_client() -> LLMClient:
    # `LEARNING_LLM=stub` swaps in a deterministic grader so demos and tests
    # never call OpenRouter or spend money; unset, the default stays
    # OpenRouter. A missing `OPENROUTER_API_KEY` only fails a `short_answer`
    # review at grading time, not startup.
    if os.environ.get("LEARNING_LLM") == "stub":
        return StubGraderClient()
    return OpenRouterClient()


# Constructed once at import time.
_llm_client: LLMClient = _build_llm_client()


def get_llm_client() -> LLMClient:
    return _llm_client


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "learning",
        "version": __version__,
        "database": "configured" if os.environ.get("DATABASE_URL") else "unconfigured",
    }


@app.get("/health/db")
async def health_db(session: AsyncSession = Depends(get_session)) -> dict:
    # A real round trip, not just "DATABASE_URL is set" (that's `/health`'s
    # job) — Railway's deploy done-check (RUNBOOK.md "Services") wants proof
    # Postgres is actually reachable, e.g. right after a migration.
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — any DB failure is this route's one job to report
        raise _error(503, "database_unavailable", str(exc)) from exc
    return {"status": "ok", "database": "reachable"}


@app.get("/whoami")
async def whoami(identity: ActingIdentity = Depends(acting_identity)) -> dict:
    return {
        "acting_identity": {
            "platform": identity.platform,
            "external_id": identity.external_id,
            "alt_id": identity.alt_id,
        }
    }


@app.post("/identities/resolve", response_model=PersonSummary)
async def identities_resolve(
    request: Request,
    body: IdentityResolveRequest,
    _: None = Depends(require_service_token),
    session: AsyncSession = Depends(get_session),
) -> PersonSummary:
    person = await resolve_identity(session, platform=body.platform, external_id=body.external_id, alt_id=body.alt_id)
    if person is None:
        # Only path that ever sees this identity — it arrives in the
        # request body, not `X-Acting-Identity` — so this warning is the
        # sole record of what failed to resolve.
        log_unknown_identity(
            path=request.url.path, platform=body.platform, external_id=body.external_id, alt_id=body.alt_id
        )
        raise _error(403, "unknown_identity", "no person matches this identity")
    return PersonSummary(
        id=person.id, display_name=person.display_name, email=person.email, is_operator=person.is_operator,
        role=person.role,
    )


@app.post("/identities/link", response_model=IdentityOut)
async def identities_link(
    body: IdentityLinkRequest,
    _: None = Depends(require_service_token),
    session: AsyncSession = Depends(get_session),
) -> IdentityOut:
    try:
        identity = await consume_link_code(
            session, code=body.code, platform=body.platform, external_id=body.external_id, alt_id=body.alt_id
        )
    except LinkCodeInvalid as exc:
        raise _error(403, "unknown_identity", "link code is unknown, expired, or already used") from exc
    except IdentityAlreadyLinked as exc:
        raise _error(422, "validation_error", "this platform identity is already linked") from exc
    return IdentityOut(
        id=identity.id,
        person_id=identity.person_id,
        platform=identity.platform,
        external_id=identity.external_id,
        alt_id=identity.alt_id,
        is_primary=identity.is_primary,
        linked_at=identity.linked_at,
    )


@app.post("/me/link-code", response_model=LinkCodeResponse)
async def me_link_code(
    request: Request,
    identity: ActingIdentity = Depends(acting_identity),
    session: AsyncSession = Depends(get_session),
) -> LinkCodeResponse:
    person = await resolve_identity(
        session, platform=identity.platform, external_id=identity.external_id, alt_id=identity.alt_id
    )
    if person is None:
        log_unknown_identity(
            path=request.url.path,
            platform=identity.platform,
            external_id=identity.external_id,
            alt_id=identity.alt_id,
        )
        raise _error(403, "unknown_identity", "no person matches this identity")
    link_code = await mint_link_code(session, person_id=person.id)
    return LinkCodeResponse(code=link_code.code, expires_at=link_code.expires_at)


from learning_service.roster.router import router as _roster_router  # noqa: E402

app.include_router(_roster_router)

from learning_service.curriculum_admin import router as _curriculum_admin_router  # noqa: E402

app.include_router(_curriculum_admin_router)

from learning_service.topics import router as _topics_router  # noqa: E402

app.include_router(_topics_router)

from learning_service.concept_graph import router as _concept_graph_router  # noqa: E402

app.include_router(_concept_graph_router)

from learning_service.engine.router import router as _engine_router  # noqa: E402

app.include_router(_engine_router)

from learning_service.admin import router as _admin_router  # noqa: E402

app.include_router(_admin_router)

from learning_service.progress.router import router as _progress_router  # noqa: E402

app.include_router(_progress_router)

from learning_service.answers import router as _answers_router  # noqa: E402

app.include_router(_answers_router)

from learning_service.notes import router as _notes_router  # noqa: E402

app.include_router(_notes_router)

from learning_service.analytics.router import router as _analytics_router  # noqa: E402

app.include_router(_analytics_router)
