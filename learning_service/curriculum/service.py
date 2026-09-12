"""CRUD and validation for course/concept/concept_edge/item/topic (spec
§Curriculum). Prerequisite edges are validated acyclic within a course on
every write; related edges are normalized lowest-id-first and carry a weight
in (0, 1]. Item payloads are validated against their kind's shape.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.curriculum.models import Concept, ConceptEdge, Course, Item, Topic, TopicConcept
from learning_service.roster.schemas import ROLES

# spec §Curriculum → Item payloads.
ITEM_KINDS = {"mcq", "self_rated", "short_answer", "teach_back"}
EDGE_KINDS = {"prerequisite", "related"}
ITEM_STATUSES = {"draft", "published"}

# kind -> keys stripped from learner-facing reads (spec §Curriculum → Item
# payloads). Shape is documented, not enforced at write time: an admin item
# write is trusted content authoring, and a missing key surfaces as a
# grading-time error (`grading` package), not a curriculum one.
_ITEM_PAYLOAD_STRIPPED_KEYS: dict[str, set[str]] = {
    "mcq": {"correct_index"},
    "self_rated": {"answer"},
    "short_answer": {"reference", "rubric"},
    "teach_back": {"reference", "rubric"},
}


class ValidationError(Exception):
    """A 422 `validation_error`: bad reference, bad enum, duplicate, etc."""


class CycleError(Exception):
    """A 422 `cycle`: this prerequisite edge would create a cycle."""


class NotFoundError(Exception):
    """No row with this id."""


def strip_item_payload(kind: str, payload: dict) -> dict:
    """Learner-facing item reads strip `correct_index`/`answer`/`reference`/
    `rubric` (spec §Curriculum → Item payloads): the explanation and
    reference answer are returned only in the review result, after grading.
    """
    stripped_keys = _ITEM_PAYLOAD_STRIPPED_KEYS[kind]
    return {k: v for k, v in payload.items() if k not in stripped_keys}


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------


async def create_course(session: AsyncSession, *, title: str, description: str = "", slug: str | None = None) -> Course:
    if slug is not None:
        duplicate = await session.execute(select(Course.id).where(Course.slug == slug).limit(1))
        if duplicate.first() is not None:
            raise ValidationError(f"course slug {slug!r} already exists")
    course = Course(title=title, description=description, slug=slug)
    session.add(course)
    await session.commit()
    return course


async def list_courses(session: AsyncSession) -> list[Course]:
    result = await session.execute(select(Course).order_by(Course.created_at, Course.id))
    return list(result.scalars().all())


async def get_course(session: AsyncSession, course_id: str) -> Course | None:
    return await session.get(Course, course_id)


async def update_course(
    session: AsyncSession,
    course_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    slug: str | None = None,
) -> Course:
    course = await session.get(Course, course_id)
    if course is None:
        raise NotFoundError(course_id)
    if title is not None:
        course.title = title
    if description is not None:
        course.description = description
    if slug is not None and slug != course.slug:
        duplicate = await session.execute(select(Course.id).where(Course.slug == slug).limit(1))
        if duplicate.first() is not None:
            raise ValidationError(f"course slug {slug!r} already exists")
        course.slug = slug
    await session.commit()
    return course


async def delete_course(session: AsyncSession, course_id: str) -> None:
    course = await session.get(Course, course_id)
    if course is None:
        raise NotFoundError(course_id)
    has_concepts = await session.execute(select(Concept.id).where(Concept.course_id == course_id).limit(1))
    if has_concepts.first() is not None:
        raise ValidationError("course has concepts; delete them first")
    await session.delete(course)
    await session.commit()


# ---------------------------------------------------------------------------
# Concept
# ---------------------------------------------------------------------------


async def create_concept(
    session: AsyncSession,
    *,
    course_id: str,
    slug: str,
    title: str,
    description: str = "",
    mastery_threshold: float = 0.85,
) -> Concept:
    if await session.get(Course, course_id) is None:
        raise ValidationError("course_id does not exist")
    duplicate = await session.execute(
        select(Concept.id).where(Concept.course_id == course_id, Concept.slug == slug).limit(1)
    )
    if duplicate.first() is not None:
        raise ValidationError(f"slug {slug!r} already exists in this course")
    concept = Concept(
        course_id=course_id,
        slug=slug,
        title=title,
        description=description,
        mastery_threshold=mastery_threshold,
    )
    session.add(concept)
    await session.commit()
    return concept


async def list_concepts(session: AsyncSession, *, course_id: str | None = None) -> list[Concept]:
    query = select(Concept)
    if course_id is not None:
        query = query.where(Concept.course_id == course_id)
    result = await session.execute(query.order_by(Concept.course_id, Concept.slug))
    return list(result.scalars().all())


async def get_concept(session: AsyncSession, concept_id: str) -> Concept | None:
    return await session.get(Concept, concept_id)


async def update_concept(
    session: AsyncSession,
    concept_id: str,
    *,
    slug: str | None = None,
    title: str | None = None,
    description: str | None = None,
    mastery_threshold: float | None = None,
) -> Concept:
    concept = await session.get(Concept, concept_id)
    if concept is None:
        raise NotFoundError(concept_id)
    if slug is not None and slug != concept.slug:
        duplicate = await session.execute(
            select(Concept.id).where(Concept.course_id == concept.course_id, Concept.slug == slug).limit(1)
        )
        if duplicate.first() is not None:
            raise ValidationError(f"slug {slug!r} already exists in this course")
        concept.slug = slug
    if title is not None:
        concept.title = title
    if description is not None:
        concept.description = description
    if mastery_threshold is not None:
        concept.mastery_threshold = mastery_threshold
    await session.commit()
    return concept


async def delete_concept(session: AsyncSession, concept_id: str) -> None:
    concept = await session.get(Concept, concept_id)
    if concept is None:
        raise NotFoundError(concept_id)
    has_items = await session.execute(select(Item.id).where(Item.concept_id == concept_id).limit(1))
    if has_items.first() is not None:
        raise ValidationError("concept has items; delete them first")
    edges = await session.execute(
        select(ConceptEdge).where(
            (ConceptEdge.from_concept_id == concept_id) | (ConceptEdge.to_concept_id == concept_id)
        )
    )
    for edge in edges.scalars().all():
        await session.delete(edge)
    await session.delete(concept)
    await session.commit()


# ---------------------------------------------------------------------------
# Concept edge
# ---------------------------------------------------------------------------


async def _would_cycle(session: AsyncSession, *, from_id: str, to_id: str, course_id: str) -> bool:
    if from_id == to_id:
        return True
    result = await session.execute(
        select(ConceptEdge.from_concept_id, ConceptEdge.to_concept_id)
        .join(Concept, Concept.id == ConceptEdge.to_concept_id)
        .where(ConceptEdge.kind == "prerequisite", Concept.course_id == course_id)
    )
    adjacency: dict[str, list[str]] = {}
    for edge_from, edge_to in result.all():
        adjacency.setdefault(edge_from, []).append(edge_to)

    # Adding from_id -> to_id closes a cycle iff to_id can already reach
    # from_id in the existing graph.
    stack = [to_id]
    seen = {to_id}
    while stack:
        node = stack.pop()
        if node == from_id:
            return True
        for neighbor in adjacency.get(node, []):
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return False


async def create_edge(
    session: AsyncSession, *, from_concept_id: str, to_concept_id: str, kind: str, weight: float = 1.0
) -> ConceptEdge:
    if kind not in EDGE_KINDS:
        raise ValidationError(f"kind must be one of {sorted(EDGE_KINDS)}")
    if from_concept_id == to_concept_id:
        raise ValidationError("an edge cannot connect a concept to itself")

    from_concept = await session.get(Concept, from_concept_id)
    to_concept = await session.get(Concept, to_concept_id)
    if from_concept is None or to_concept is None:
        raise ValidationError("from_concept_id and to_concept_id must both exist")

    if kind == "prerequisite":
        if from_concept.course_id != to_concept.course_id:
            raise ValidationError("prerequisite edges must connect concepts in the same course")
        if await _would_cycle(session, from_id=from_concept_id, to_id=to_concept_id, course_id=from_concept.course_id):
            raise CycleError(f"{from_concept_id} -> {to_concept_id} would create a cycle")
    else:
        if not (0 < weight <= 1):
            raise ValidationError("related edge weight must be in (0, 1]")
        # Related edges are undirected in meaning; store once, lowest id first.
        if from_concept_id > to_concept_id:
            from_concept_id, to_concept_id = to_concept_id, from_concept_id

    duplicate = await session.execute(
        select(ConceptEdge.id).where(
            ConceptEdge.from_concept_id == from_concept_id,
            ConceptEdge.to_concept_id == to_concept_id,
            ConceptEdge.kind == kind,
        )
    )
    if duplicate.first() is not None:
        raise ValidationError("this edge already exists")

    edge = ConceptEdge(from_concept_id=from_concept_id, to_concept_id=to_concept_id, kind=kind, weight=weight)
    session.add(edge)
    await session.commit()
    return edge


async def list_edges(
    session: AsyncSession, *, course_id: str | None = None, concept_id: str | None = None, kind: str | None = None
) -> list[ConceptEdge]:
    query = select(ConceptEdge)
    if kind is not None:
        query = query.where(ConceptEdge.kind == kind)
    if concept_id is not None:
        query = query.where(
            (ConceptEdge.from_concept_id == concept_id) | (ConceptEdge.to_concept_id == concept_id)
        )
    if course_id is not None:
        from_concept = Concept.__table__.alias("from_concept")
        to_concept = Concept.__table__.alias("to_concept")
        query = (
            query.join(from_concept, from_concept.c.id == ConceptEdge.from_concept_id)
            .join(to_concept, to_concept.c.id == ConceptEdge.to_concept_id)
            .where((from_concept.c.course_id == course_id) | (to_concept.c.course_id == course_id))
        )
    result = await session.execute(query.order_by(ConceptEdge.id))
    return list(result.scalars().all())


async def update_edge_weight(session: AsyncSession, edge_id: str, *, weight: float) -> ConceptEdge:
    edge = await session.get(ConceptEdge, edge_id)
    if edge is None:
        raise NotFoundError(edge_id)
    if edge.kind == "related" and not (0 < weight <= 1):
        raise ValidationError("related edge weight must be in (0, 1]")
    edge.weight = weight
    await session.commit()
    return edge


async def delete_edge(session: AsyncSession, edge_id: str) -> None:
    edge = await session.get(ConceptEdge, edge_id)
    if edge is None:
        raise NotFoundError(edge_id)
    await session.delete(edge)
    await session.commit()


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------


async def create_item(
    session: AsyncSession,
    *,
    concept_id: str,
    kind: str,
    prompt: str,
    payload: dict | None = None,
    status: str = "draft",
) -> Item:
    if kind not in ITEM_KINDS:
        raise ValidationError(f"kind must be one of {sorted(ITEM_KINDS)}")
    if status not in ITEM_STATUSES:
        raise ValidationError(f"status must be one of {sorted(ITEM_STATUSES)}")
    if await session.get(Concept, concept_id) is None:
        raise ValidationError("concept_id does not exist")
    item = Item(concept_id=concept_id, kind=kind, prompt=prompt, payload=payload or {}, status=status)
    session.add(item)
    await session.commit()
    return item


async def list_items(
    session: AsyncSession, *, concept_id: str | None = None, status: str | None = None
) -> list[Item]:
    query = select(Item)
    if concept_id is not None:
        query = query.where(Item.concept_id == concept_id)
    if status is not None:
        query = query.where(Item.status == status)
    result = await session.execute(query.order_by(Item.created_at, Item.id))
    return list(result.scalars().all())


async def get_item(session: AsyncSession, item_id: str) -> Item | None:
    return await session.get(Item, item_id)


async def update_item(
    session: AsyncSession,
    item_id: str,
    *,
    prompt: str | None = None,
    payload: dict | None = None,
) -> Item:
    item = await session.get(Item, item_id)
    if item is None:
        raise NotFoundError(item_id)
    if prompt is not None:
        item.prompt = prompt
    if payload is not None:
        item.payload = payload
    await session.commit()
    return item


async def publish_item(session: AsyncSession, item_id: str) -> Item:
    item = await session.get(Item, item_id)
    if item is None:
        raise NotFoundError(item_id)
    item.status = "published"
    await session.commit()
    return item


async def delete_item(session: AsyncSession, item_id: str) -> None:
    item = await session.get(Item, item_id)
    if item is None:
        raise NotFoundError(item_id)
    await session.delete(item)
    await session.commit()


# ---------------------------------------------------------------------------
# Topic (OPEN-QUESTIONS.md Q6): a named subgraph of a course — one per
# persona/role.
# ---------------------------------------------------------------------------


async def create_topic(
    session: AsyncSession,
    *,
    course_id: str,
    slug: str,
    title: str,
    persona_role: str,
    entry_concept_id: str,
    concept_ids: list[str],
    grounded_in: list[str],
    description: str = "",
) -> Topic:
    if not grounded_in:
        raise ValidationError("grounded_in must name at least one source artifact")
    if persona_role not in ROLES:
        raise ValidationError(f"persona_role must be one of {sorted(ROLES)}")
    if await session.get(Course, course_id) is None:
        raise ValidationError("course_id does not exist")
    if await session.get(Concept, entry_concept_id) is None:
        raise ValidationError("entry_concept_id does not exist")
    if entry_concept_id not in concept_ids:
        raise ValidationError("entry_concept_id must be one of concept_ids")
    for concept_id in concept_ids:
        if await session.get(Concept, concept_id) is None:
            raise ValidationError(f"concept_id {concept_id!r} does not exist")
    duplicate = await session.execute(
        select(Topic.id).where(Topic.course_id == course_id, Topic.slug == slug).limit(1)
    )
    if duplicate.first() is not None:
        raise ValidationError(f"slug {slug!r} already exists in this course")

    topic = Topic(
        course_id=course_id,
        slug=slug,
        title=title,
        description=description,
        persona_role=persona_role,
        entry_concept_id=entry_concept_id,
        grounded_in=list(grounded_in),
    )
    session.add(topic)
    await session.flush()
    for concept_id in concept_ids:
        session.add(TopicConcept(topic_id=topic.id, concept_id=concept_id))
    await session.commit()
    return topic


async def list_topics(
    session: AsyncSession, *, course_id: str | None = None, persona_role: str | None = None
) -> list[Topic]:
    query = select(Topic)
    if course_id is not None:
        query = query.where(Topic.course_id == course_id)
    if persona_role is not None:
        query = query.where(Topic.persona_role == persona_role)
    result = await session.execute(query.order_by(Topic.course_id, Topic.slug))
    return list(result.scalars().all())


async def topic_concept_ids(session: AsyncSession, topic_id: str) -> list[str]:
    result = await session.execute(select(TopicConcept.concept_id).where(TopicConcept.topic_id == topic_id))
    return [row[0] for row in result.all()]
