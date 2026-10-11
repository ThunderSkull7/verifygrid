"""Verification runs and discrepancies tables

Revision ID: 0002_verification_runs
Revises: 0001_initial_tables
Create Date: 2026-10-11 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_verification_runs"
down_revision: Union[str, None] = "0001_initial_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. verification_runs table
    op.create_table(
        "verification_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_file_id", sa.Uuid(), nullable=True),
        sa.Column("target_file_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("key_columns", sa.JSON(), nullable=False),
        sa.Column("column_mapping", sa.JSON(), nullable=True),
        sa.Column("configuration", sa.JSON(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_file_id"], ["source_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_file_id"], ["source_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_verification_runs_project_id"), "verification_runs", ["project_id"], unique=False)
    op.create_index(op.f("ix_verification_runs_source_file_id"), "verification_runs", ["source_file_id"], unique=False)
    op.create_index(op.f("ix_verification_runs_target_file_id"), "verification_runs", ["target_file_id"], unique=False)
    op.create_index(op.f("ix_verification_runs_status"), "verification_runs", ["status"], unique=False)

    # 2. verification_discrepancies table
    op.create_table(
        "verification_discrepancies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("match_status", sa.String(length=50), nullable=False),
        sa.Column("discrepancy_category", sa.String(length=50), nullable=False),
        sa.Column("key_values", sa.JSON(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("target_row_number", sa.Integer(), nullable=True),
        sa.Column("source_row_numbers", sa.JSON(), nullable=True),
        sa.Column("target_row_numbers", sa.JSON(), nullable=True),
        sa.Column("source_record", sa.JSON(), nullable=True),
        sa.Column("target_record", sa.JSON(), nullable=True),
        sa.Column("field_differences", sa.JSON(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["verification_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_verification_discrepancies_run_id"), "verification_discrepancies", ["run_id"], unique=False)
    op.create_index(op.f("ix_verification_discrepancies_match_status"), "verification_discrepancies", ["match_status"], unique=False)
    op.create_index(op.f("ix_verification_discrepancies_discrepancy_category"), "verification_discrepancies", ["discrepancy_category"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_verification_discrepancies_discrepancy_category"), table_name="verification_discrepancies")
    op.drop_index(op.f("ix_verification_discrepancies_match_status"), table_name="verification_discrepancies")
    op.drop_index(op.f("ix_verification_discrepancies_run_id"), table_name="verification_discrepancies")
    op.drop_table("verification_discrepancies")

    op.drop_index(op.f("ix_verification_runs_status"), table_name="verification_runs")
    op.drop_index(op.f("ix_verification_runs_target_file_id"), table_name="verification_runs")
    op.drop_index(op.f("ix_verification_runs_source_file_id"), table_name="verification_runs")
    op.drop_index(op.f("ix_verification_runs_project_id"), table_name="verification_runs")
    op.drop_table("verification_runs")
