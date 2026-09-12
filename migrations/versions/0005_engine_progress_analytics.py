"""engine/progress/analytics: review, card_state, concept_state, answer,
learner_note, audit

Revision ID: 0005_engine_progress_analytics
Revises: 0004_focus
Create Date: 2026-09-12
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_engine_progress_analytics"
down_revision: Union[str, None] = "0004_focus"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("person_id", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("grade", sa.Float(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("asserted_by", sa.String(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("bypassed", sa.Boolean(), nullable=False),
        sa.Column("concept_id", sa.String(), nullable=True),
        sa.Column("p_known_after", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "idempotency_key", name="uq_review_person_idempotency_key"),
    )
    op.create_index("ix_review_person_id", "review", ["person_id"])
    op.create_index("ix_review_item_id", "review", ["item_id"])

    op.create_table(
        "card_state",
        sa.Column("person_id", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("stability", sa.Float(), nullable=False),
        sa.Column("difficulty", sa.Float(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("lapses", sa.Integer(), nullable=False),
        sa.Column("last_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("person_id", "item_id"),
    )

    op.create_table(
        "concept_state",
        sa.Column("person_id", sa.String(), nullable=False),
        sa.Column("concept_id", sa.String(), nullable=False),
        sa.Column("p_known", sa.Float(), nullable=False),
        sa.Column("reviews", sa.Integer(), nullable=False),
        sa.Column("last_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("person_id", "concept_id"),
    )

    op.create_table(
        "answer",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("review_id", sa.String(), nullable=False),
        sa.Column("person_id", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_answer_person_id", "answer", ["person_id"])
    op.create_index("ix_answer_created_at", "answer", ["created_at"])

    op.create_table(
        "learner_note",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("person_id", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learner_note_person_id", "learner_note", ["person_id"])

    op.create_table(
        "audit",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("actor_person_id", sa.String(), nullable=False),
        sa.Column("subject_scope", sa.String(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_actor_person_id", "audit", ["actor_person_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_actor_person_id", table_name="audit")
    op.drop_table("audit")

    op.drop_index("ix_learner_note_person_id", table_name="learner_note")
    op.drop_table("learner_note")

    op.drop_index("ix_answer_created_at", table_name="answer")
    op.drop_index("ix_answer_person_id", table_name="answer")
    op.drop_table("answer")

    op.drop_table("concept_state")
    op.drop_table("card_state")

    op.drop_index("ix_review_item_id", table_name="review")
    op.drop_index("ix_review_person_id", table_name="review")
    op.drop_table("review")
