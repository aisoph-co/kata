"""curriculum: course, concept, concept_edge, item, topic, topic_concept

Revision ID: 0003_curriculum
Revises: 0002_link_code
Create Date: 2026-09-12
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_curriculum"
down_revision: Union[str, None] = "0002_link_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "course",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_course_slug"),
    )
    op.create_table(
        "concept",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("mastery_threshold", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["course.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "slug", name="uq_concept_course_slug"),
    )
    op.create_table(
        "concept_edge",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("from_concept_id", sa.String(), nullable=False),
        sa.Column("to_concept_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["from_concept_id"], ["concept.id"]),
        sa.ForeignKeyConstraint(["to_concept_id"], ["concept.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("from_concept_id", "to_concept_id", "kind", name="uq_concept_edge_from_to_kind"),
    )
    op.create_table(
        "item",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("concept_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "topic",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("course_id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("persona_role", sa.String(), nullable=False),
        sa.Column("entry_concept_id", sa.String(), nullable=False),
        sa.Column("grounded_in", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.ForeignKeyConstraint(["course_id"], ["course.id"]),
        sa.ForeignKeyConstraint(["entry_concept_id"], ["concept.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "slug", name="uq_topic_course_slug"),
    )
    op.create_table(
        "topic_concept",
        sa.Column("topic_id", sa.String(), nullable=False),
        sa.Column("concept_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topic.id"]),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"]),
        sa.PrimaryKeyConstraint("topic_id", "concept_id"),
    )

    op.create_index("ix_concept_course_id", "concept", ["course_id"])
    op.create_index("ix_item_concept_id", "item", ["concept_id"])
    op.create_index("ix_topic_course_id", "topic", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_topic_course_id", table_name="topic")
    op.drop_index("ix_item_concept_id", table_name="item")
    op.drop_index("ix_concept_course_id", table_name="concept")
    op.drop_table("topic_concept")
    op.drop_table("topic")
    op.drop_table("item")
    op.drop_table("concept_edge")
    op.drop_table("concept")
    op.drop_table("course")
