"""`/admin/courses`, `/admin/concepts`, `/admin/edges`, `/admin/items` (US-C1,
AGCTM-38, spec §Curriculum, §API): operator CRUD for the concept graph.

`is_operator` is required on every route here (spec §API, "Authentication").
Prerequisite edge writes are validated acyclic within a course -> 422 `cycle`
on violation (`curriculum.service._would_cycle`); `POST
/admin/items/{id}/publish` flips an item from `draft` to `published`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.curriculum import service as curriculum_service
from learning_service.curriculum.models import DEFAULT_MASTERY_THRESHOLD, Concept, ConceptEdge, Course, Item, Topic
from learning_service.db import get_session
from learning_service.main import _error, require_operator

router = APIRouter()


def _course_out(course: Course) -> dict[str, Any]:
    return {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "slug": course.slug,
        "created_at": course.created_at.isoformat(),
    }


def _concept_out(concept: Concept) -> dict[str, Any]:
    return {
        "id": concept.id,
        "course_id": concept.course_id,
        "slug": concept.slug,
        "title": concept.title,
        "description": concept.description,
        "mastery_threshold": concept.mastery_threshold,
    }


def _edge_out(edge: ConceptEdge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "from_concept_id": edge.from_concept_id,
        "to_concept_id": edge.to_concept_id,
        "kind": edge.kind,
        "weight": edge.weight,
    }


def _topic_out(topic: Topic, concept_ids: list[str]) -> dict[str, Any]:
    return {
        "id": topic.id,
        "course_id": topic.course_id,
        "slug": topic.slug,
        "title": topic.title,
        "description": topic.description,
        "persona_role": topic.persona_role,
        "entry_concept_id": topic.entry_concept_id,
        "concept_ids": concept_ids,
        "grounded_in": list(topic.grounded_in or []),
    }


def _item_out(item: Item) -> dict[str, Any]:
    return {
        "id": item.id,
        "concept_id": item.concept_id,
        "kind": item.kind,
        "prompt": item.prompt,
        "payload": item.payload,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
    }


def _not_found(exc: curriculum_service.NotFoundError, what: str) -> Exception:
    return _error(404, "not_found", f"{what} not found")


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


class CourseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    description: str = ""
    slug: str | None = Field(default=None, min_length=1)


class CourseUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    slug: str | None = Field(default=None, min_length=1)


@router.post("/admin/courses", status_code=201)
async def create_course(
    body: CourseCreateRequest,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        course = await curriculum_service.create_course(
            session, title=body.title, description=body.description, slug=body.slug
        )
    except curriculum_service.ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc
    return _course_out(course)


@router.get("/admin/courses")
async def list_courses(
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    courses = await curriculum_service.list_courses(session)
    return {"courses": [_course_out(c) for c in courses]}


@router.get("/admin/courses/{course_id}")
async def get_course(
    course_id: str,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    course = await curriculum_service.get_course(session, course_id)
    if course is None:
        raise _error(404, "not_found", "course not found")
    return _course_out(course)


@router.patch("/admin/courses/{course_id}")
async def update_course(
    course_id: str,
    body: CourseUpdateRequest,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        course = await curriculum_service.update_course(
            session, course_id, title=body.title, description=body.description, slug=body.slug
        )
    except curriculum_service.NotFoundError as exc:
        raise _not_found(exc, "course") from exc
    except curriculum_service.ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc
    return _course_out(course)


@router.delete("/admin/courses/{course_id}", status_code=204)
async def delete_course(
    course_id: str,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await curriculum_service.delete_course(session, course_id)
    except curriculum_service.NotFoundError as exc:
        raise _not_found(exc, "course") from exc
    except curriculum_service.ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Concepts
# ---------------------------------------------------------------------------


class ConceptCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: str
    slug: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD


class ConceptUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    mastery_threshold: float | None = None


@router.post("/admin/concepts", status_code=201)
async def create_concept(
    body: ConceptCreateRequest,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        concept = await curriculum_service.create_concept(
            session,
            course_id=body.course_id,
            slug=body.slug,
            title=body.title,
            description=body.description,
            mastery_threshold=body.mastery_threshold,
        )
    except curriculum_service.ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc
    return _concept_out(concept)


@router.get("/admin/concepts")
async def list_concepts(
    course_id: str | None = Query(default=None),
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    concepts = await curriculum_service.list_concepts(session, course_id=course_id)
    return {"concepts": [_concept_out(c) for c in concepts]}


@router.get("/admin/concepts/{concept_id}")
async def get_concept(
    concept_id: str,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    concept = await curriculum_service.get_concept(session, concept_id)
    if concept is None:
        raise _error(404, "not_found", "concept not found")
    return _concept_out(concept)


@router.patch("/admin/concepts/{concept_id}")
async def update_concept(
    concept_id: str,
    body: ConceptUpdateRequest,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        concept = await curriculum_service.update_concept(
            session,
            concept_id,
            slug=body.slug,
            title=body.title,
            description=body.description,
            mastery_threshold=body.mastery_threshold,
        )
    except curriculum_service.NotFoundError as exc:
        raise _not_found(exc, "concept") from exc
    except curriculum_service.ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc
    return _concept_out(concept)


@router.delete("/admin/concepts/{concept_id}", status_code=204)
async def delete_concept(
    concept_id: str,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await curriculum_service.delete_concept(session, concept_id)
    except curriculum_service.NotFoundError as exc:
        raise _not_found(exc, "concept") from exc
    except curriculum_service.ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


class EdgeCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_concept_id: str
    to_concept_id: str
    kind: str
    weight: float = 1.0


class EdgeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weight: float


@router.post("/admin/edges", status_code=201)
async def create_edge(
    body: EdgeCreateRequest,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        edge = await curriculum_service.create_edge(
            session,
            from_concept_id=body.from_concept_id,
            to_concept_id=body.to_concept_id,
            kind=body.kind,
            weight=body.weight,
        )
    except curriculum_service.CycleError as exc:
        raise _error(422, "cycle", str(exc)) from exc
    except curriculum_service.ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc
    return _edge_out(edge)


@router.get("/admin/edges")
async def list_edges(
    course_id: str | None = Query(default=None),
    concept_id: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    edges = await curriculum_service.list_edges(session, course_id=course_id, concept_id=concept_id, kind=kind)
    return {"edges": [_edge_out(e) for e in edges]}


@router.patch("/admin/edges/{edge_id}")
async def update_edge(
    edge_id: str,
    body: EdgeUpdateRequest,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        edge = await curriculum_service.update_edge_weight(session, edge_id, weight=body.weight)
    except curriculum_service.NotFoundError as exc:
        raise _not_found(exc, "edge") from exc
    except curriculum_service.ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc
    return _edge_out(edge)


@router.delete("/admin/edges/{edge_id}", status_code=204)
async def delete_edge(
    edge_id: str,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await curriculum_service.delete_edge(session, edge_id)
    except curriculum_service.NotFoundError as exc:
        raise _not_found(exc, "edge") from exc
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


class ItemCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concept_id: str
    kind: str
    prompt: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "draft"


class ItemUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str | None = Field(default=None, min_length=1)
    payload: dict[str, Any] | None = None


@router.post("/admin/items", status_code=201)
async def create_item(
    body: ItemCreateRequest,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        item = await curriculum_service.create_item(
            session,
            concept_id=body.concept_id,
            kind=body.kind,
            prompt=body.prompt,
            payload=body.payload,
            status=body.status,
        )
    except curriculum_service.ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc
    return _item_out(item)


@router.get("/admin/items")
async def list_items(
    concept_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    items = await curriculum_service.list_items(session, concept_id=concept_id, status=status)
    return {"items": [_item_out(i) for i in items]}


@router.get("/admin/items/{item_id}")
async def get_item(
    item_id: str,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    item = await curriculum_service.get_item(session, item_id)
    if item is None:
        raise _error(404, "not_found", "item not found")
    return _item_out(item)


@router.patch("/admin/items/{item_id}")
async def update_item(
    item_id: str,
    body: ItemUpdateRequest,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        item = await curriculum_service.update_item(session, item_id, prompt=body.prompt, payload=body.payload)
    except curriculum_service.NotFoundError as exc:
        raise _not_found(exc, "item") from exc
    return _item_out(item)


@router.post("/admin/items/{item_id}/publish")
async def publish_item(
    item_id: str,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        item = await curriculum_service.publish_item(session, item_id)
    except curriculum_service.NotFoundError as exc:
        raise _not_found(exc, "item") from exc
    return _item_out(item)


@router.delete("/admin/items/{item_id}", status_code=204)
async def delete_item(
    item_id: str,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await curriculum_service.delete_item(session, item_id)
    except curriculum_service.NotFoundError as exc:
        raise _not_found(exc, "item") from exc
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Topics (Contract v1.2.0)
# ---------------------------------------------------------------------------


class TopicCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: str
    slug: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    persona_role: str
    entry_concept_id: str
    concept_ids: list[str] = Field(min_length=1)
    # Emptiness is checked in `curriculum_service.create_topic`, not with
    # `Field(min_length=1)`: a pydantic-level failure returns FastAPI's own
    # error body, and `openapi.yaml` documents this route's 422 as this
    # service's `ValidationError` envelope for every other bad field.
    grounded_in: list[str] = []


@router.post("/admin/topics", status_code=201)
async def create_topic(
    body: TopicCreateRequest,
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        topic = await curriculum_service.create_topic(
            session,
            course_id=body.course_id,
            slug=body.slug,
            title=body.title,
            description=body.description,
            persona_role=body.persona_role,
            entry_concept_id=body.entry_concept_id,
            concept_ids=body.concept_ids,
            grounded_in=body.grounded_in,
        )
    except curriculum_service.ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc
    concept_ids = await curriculum_service.topic_concept_ids(session, topic.id)
    return _topic_out(topic, concept_ids)
