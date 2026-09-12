"""The Kata learning service's core app (spec §API): identity resolution,
roster admin, curriculum/concept-graph, CI1's ingestion trigger
(`build-day/issues.md` "CI1", KATA-13), and — as of KATA-3 — the learning
engine, grading, team analytics, privacy and audit surface: `/me/next`,
`/me/reviews`, `/me/progress`, `/me/due-summary`, `/me/answers`,
`/me/notes*`, `/team/*`, and `/admin/replay`. Those live in their own router
modules (`reviews.py`, `progress.py`, `answers.py`, `notes.py`, `team.py`,
`admin_replay.py`), included at the bottom of this file the same way
`admin.py`/`curriculum_admin.py`/`topics.py`/`concept_graph.py`/
`ingestion.py` already are.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service import __version__
from learning_service.db import get_session, session_scope
from learning_service.extraction.client import ExtractionClient, OpenRouterExtractionClient
from learning_service.extraction.sources import concept_frequency, load_context_issues
from learning_service.extraction.stub import StubExtractionClient
from learning_service.identity.models import Base
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

# `learning_service.curriculum.models`, `.engine.models`, `.privacy.models`
# all share `identity.models.Base` (`Base.metadata.create_all()` below picks
# them up automatically), but each must still be imported somewhere before
# that call so its tables register on `Base.metadata` — these imports are
# that, kept for their side effect.
from learning_service.curriculum import models as _curriculum_models  # noqa: F401
from learning_service.engine import models as _engine_models  # noqa: F401
from learning_service.privacy import models as _privacy_models  # noqa: F401


def _build_extraction_client() -> ExtractionClient:
    # CI1's `GET /admin/ingest` (`ingestion.py`) needs an LLM to classify a
    # co-occurring concept pair and draft an item — `LEARNING_LLM=stub`
    # selects a deterministic `StubExtractionClient` (its frequency table
    # built from the same seeded `issues.jsonl` ingestion itself reads) for
    # demos and tests; unset stays the real `OpenRouterExtractionClient`. A
    # missing `OPENROUTER_API_KEY` only fails ingestion at request time
    # (surfaced as `event: error`), not startup.
    if os.environ.get("LEARNING_LLM") == "stub":
        return StubExtractionClient(concept_frequency(load_context_issues()))
    return OpenRouterExtractionClient()


# Constructed once at import time so every request reuses the same client
# instead of rebuilding it (and, in the stub case, re-reading the fixture)
# per call.
_extraction_client: ExtractionClient = _build_extraction_client()


def get_extraction_client() -> ExtractionClient:
    return _extraction_client


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    # No alembic chain in this package yet (KATA-2's follow-up issue adds
    # `engine`/`analytics` tables and is the natural point to introduce real
    # migrations). Until then, a configured `DATABASE_URL` gets its schema
    # from `Base.metadata.create_all()` — safe to run on every boot since it
    # only creates tables that don't already exist.
    if os.environ.get("DATABASE_URL"):
        async with session_scope() as session:
            conn = await session.connection()
            await conn.run_sync(Base.metadata.create_all)
            # PostgreSQL makes DDL transactional.  `session_scope()` closes
            # without an implicit commit, so persist the schema before the
            # seed opens its separate session below.
            await session.commit()

        # `LEARNING_SEED=ferry` (spec §Deployment, "Demo seed"): loads the
        # named scenario once per database, so the golden demo's 60 days of
        # history are there the first time anything reads it. Unset is a
        # no-op; `learning_service.seed` is idempotent across restarts.
        scenario_name = os.environ.get("LEARNING_SEED")
        if scenario_name:
            from learning_service.seed import seed

            async with session_scope() as session:
                await seed(session, scenario_name)
    yield


app = FastAPI(title="Kata learning service", version=__version__, lifespan=_lifespan)


@app.middleware("http")
async def _log_request(request: Request, call_next):
    # `/health` is Railway's liveness probe — it fires every few seconds and
    # would otherwise drown out the requests an operator actually cares
    # about, so it's the one path excluded here.
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
    # Two trusted callers share this dependency (web-app-design.md Contract
    # change #7): Hermes's `SERVICE_TOKEN` and the web app's own
    # `WEB_SERVICE_TOKEN`, checked identically — the acting identity, not the
    # token, says who is calling (e.g. `X-Acting-Identity: web:<subject>`).
    # Unset tokens are dropped, so a misconfigured service still fails closed.
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
    """Every `/me/*` route's acting person (spec §Identity: "the acting
    person is resolved before any handler runs... unknown identities are
    rejected") — exact `platform`+`external_id`, then `alt_id`. An
    unresolvable identity is `403 unknown_identity`, same as `/team/*` and
    `require_operator`.
    """
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


@app.get("/health")
async def health() -> dict:
    from learning_service.seed import SCENARIOS

    seed_env = os.environ.get("LEARNING_SEED")
    return {
        "status": "ok",
        "service": "learning",
        "version": __version__,
        "database": "configured" if os.environ.get("DATABASE_URL") else "unconfigured",
        "seed": seed_env if seed_env in SCENARIOS else "none",
    }


@app.get("/health/db")
async def health_db() -> dict:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise _error(503, "database_unconfigured", "DATABASE_URL is not set")
    import asyncpg

    try:
        conn = await asyncpg.connect(url, timeout=10)
        try:
            version = await conn.fetchval("select version()")
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001 — surface the driver's message
        raise _error(503, "database_unreachable", str(exc)) from exc
    return {"status": "ok", "postgres": version.split(" on ")[0]}


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
    person = await resolve_identity(
        session, platform=body.platform, external_id=body.external_id, alt_id=body.alt_id
    )
    if person is None:
        # Only path that ever sees this identity — it arrives in the
        # request body, not `X-Acting-Identity` — so this warning is the
        # sole record of what failed to resolve.
        log_unknown_identity(
            path=request.url.path,
            platform=body.platform,
            external_id=body.external_id,
            alt_id=body.alt_id,
        )
        raise _error(403, "unknown_identity", "no person matches this identity")
    return PersonSummary(
        id=person.id,
        display_name=person.display_name,
        email=person.email,
        is_operator=person.is_operator,
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


from learning_service.admin import router as _admin_router  # noqa: E402

app.include_router(_admin_router)

from learning_service.curriculum_admin import router as _curriculum_admin_router  # noqa: E402

app.include_router(_curriculum_admin_router)

from learning_service.topics import router as _topics_router  # noqa: E402

app.include_router(_topics_router)

from learning_service.concept_graph import router as _concept_graph_router  # noqa: E402

app.include_router(_concept_graph_router)

from learning_service.ingestion import router as _ingestion_router  # noqa: E402

app.include_router(_ingestion_router)

from learning_service.reviews import router as _reviews_router  # noqa: E402

app.include_router(_reviews_router)

from learning_service.progress import router as _progress_router  # noqa: E402

app.include_router(_progress_router)

from learning_service.answers import router as _answers_router  # noqa: E402

app.include_router(_answers_router)

from learning_service.notes import router as _notes_router  # noqa: E402

app.include_router(_notes_router)

from learning_service.team import router as _team_router  # noqa: E402

app.include_router(_team_router)

from learning_service.admin_replay import router as _admin_replay_router  # noqa: E402

app.include_router(_admin_replay_router)
