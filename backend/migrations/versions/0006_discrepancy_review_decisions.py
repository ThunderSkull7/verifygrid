"""Create discrepancy_review_decisions table

Batch 26C implementation per Batch 23 contract (§5) and Batch 24 retention
decision D8 (RESTRICT foreign keys).

Revision ID: 0006_discrepancy_review_decisions
Revises: 0005_verification_templates
Create Date: 2026-10-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006_discrepancy_review_decisions"
down_revision: Union[str, None] = "0005_verification_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discrepancy_review_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("discrepancy_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=50), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("reviewer_id", sa.String(length=100), nullable=True),
        sa.Column("reviewer_email", sa.String(length=255), nullable=True),
        sa.Column("previous_status", sa.String(length=50), nullable=True),
        sa.Column("new_status", sa.String(length=50), nullable=False),
        sa.Column("is_bulk_action", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cluster_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["discrepancy_id"],
            ["verification_discrepancies.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["verification_runs.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_discrepancy_review_decisions_cluster_id",
        "discrepancy_review_decisions",
        ["cluster_id"],
    )
    op.create_index(
        "ix_discrepancy_review_decisions_discrepancy_id",
        "discrepancy_review_decisions",
        ["discrepancy_id"],
    )
    op.create_index(
        "ix_discrepancy_review_decisions_reviewer_id",
        "discrepancy_review_decisions",
        ["reviewer_id"],
    )
    op.create_index(
        "ix_discrepancy_review_decisions_run_id",
        "discrepancy_review_decisions",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_discrepancy_review_decisions_run_id",
        table_name="discrepancy_review_decisions",
    )
    op.drop_index(
        "ix_discrepancy_review_decisions_reviewer_id",
        table_name="discrepancy_review_decisions",
    )
    op.drop_index(
        "ix_discrepancy_review_decisions_discrepancy_id",
        table_name="discrepancy_review_decisions",
    )
    op.drop_index(
        "ix_discrepancy_review_decisions_cluster_id",
        table_name="discrepancy_review_decisions",
    )
    op.drop_table("discrepancy_review_decisions")
