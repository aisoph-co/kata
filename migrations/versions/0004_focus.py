"""focus: manager-set boost to next-item selection

Revision ID: 0004_focus
Revises: 0003_curriculum
Create Date: 2026-09-12
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_focus"
down_revision: Union[str, None] = "0003_curriculum"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "focus",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("scope_kind", sa.String(), nullable=False),
        sa.Column("scope_person_id", sa.String(), nullable=False),
        sa.Column("concept_id", sa.String(), nullable=False),
        sa.Column("set_by", sa.String(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scope_person_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"]),
        sa.ForeignKeyConstraint(["set_by"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_focus_scope_person_id", "focus", ["scope_person_id"])
    op.create_index("ix_focus_concept_id", "focus", ["concept_id"])


def downgrade() -> None:
    op.drop_index("ix_focus_concept_id", table_name="focus")
    op.drop_index("ix_focus_scope_person_id", table_name="focus")
    op.drop_table("focus")
