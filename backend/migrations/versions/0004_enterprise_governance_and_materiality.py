"""Add enterprise governance, materiality, clustering, and audit events

Revision ID: 0004_enterprise_governance
Revises: 0003_user_password
Create Date: 2026-10-26 16:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_enterprise_governance"
down_revision: Union[str, None] = "0003_user_password"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update users table with role
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=50), nullable=False, server_default="MAKER"),
    )

    # 2. Update verification_runs with sources and sign-off governance fields
    op.add_column("verification_runs", sa.Column("sources", sa.JSON(), nullable=True))
    op.add_column(
        "verification_runs",
        sa.Column("sign_off_status", sa.String(length=50), nullable=False, server_default="DRAFT"),
    )
    op.add_column("verification_runs", sa.Column("sign_off_proposed_by", sa.Uuid(), nullable=True))
    op.add_column("verification_runs", sa.Column("sign_off_proposed_by_name", sa.String(length=255), nullable=True))
    op.add_column("verification_runs", sa.Column("sign_off_proposal_note", sa.Text(), nullable=True))
    op.add_column("verification_runs", sa.Column("sign_off_proposed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("verification_runs", sa.Column("sign_off_approved_by", sa.Uuid(), nullable=True))
    op.add_column("verification_runs", sa.Column("sign_off_approved_by_name", sa.String(length=255), nullable=True))
    op.add_column("verification_runs", sa.Column("sign_off_decision_note", sa.Text(), nullable=True))
    op.add_column("verification_runs", sa.Column("sign_off_decided_at", sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key(
        "fk_runs_sign_off_proposed_by_users",
        "verification_runs",
        "users",
        ["sign_off_proposed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_runs_sign_off_approved_by_users",
        "verification_runs",
        "users",
        ["sign_off_approved_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_verification_runs_sign_off_status"), "verification_runs", ["sign_off_status"], unique=False)

    # 3. Update verification_discrepancies with materiality, clustering, and review fields
    op.add_column("verification_discrepancies", sa.Column("source_row_indices", sa.JSON(), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("source_records", sa.JSON(), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("child_records", sa.JSON(), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("aggregated_amount", sa.Float(), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("expected_amount", sa.Float(), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("source_amount", sa.Float(), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("target_amount", sa.Float(), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("variance_amount", sa.Float(), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("exposure_amount", sa.Float(), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("currency", sa.String(length=10), nullable=True, server_default="USD"))
    op.add_column("verification_discrepancies", sa.Column("severity", sa.String(length=20), nullable=True, server_default="medium"))
    op.add_column("verification_discrepancies", sa.Column("resolution_status", sa.String(length=30), nullable=True, server_default="unresolved"))
    op.add_column("verification_discrepancies", sa.Column("resolution_note", sa.Text(), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("resolved_by", sa.String(length=100), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("cluster_id", sa.String(length=64), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("cluster_name", sa.String(length=255), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("assigned_to", sa.String(length=100), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("side_by_side", sa.JSON(), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("reason_code", sa.String(length=100), nullable=True))
    op.add_column("verification_discrepancies", sa.Column("confidence_score", sa.Float(), nullable=True))

    op.create_index(op.f("ix_verification_discrepancies_exposure_amount"), "verification_discrepancies", ["exposure_amount"], unique=False)
    op.create_index(op.f("ix_verification_discrepancies_severity"), "verification_discrepancies", ["severity"], unique=False)
    op.create_index(op.f("ix_verification_discrepancies_resolution_status"), "verification_discrepancies", ["resolution_status"], unique=False)
    op.create_index(op.f("ix_verification_discrepancies_cluster_id"), "verification_discrepancies", ["cluster_id"], unique=False)
    op.create_index(op.f("ix_verification_discrepancies_assigned_to"), "verification_discrepancies", ["assigned_to"], unique=False)
    op.create_index(op.f("ix_verification_discrepancies_reason_code"), "verification_discrepancies", ["reason_code"], unique=False)

    # 4. Create audit_events table with tamper-evident chaining
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("user_email", sa.String(length=255), nullable=True),
        sa.Column("user_role", sa.String(length=50), nullable=False, server_default="MAKER"),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("timestamp_str", sa.String(length=64), nullable=False),
        sa.Column("event_payload", sa.JSON(), nullable=False),
        sa.Column("previous_event_hash", sa.String(length=64), nullable=False),
        sa.Column("current_event_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["verification_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_event_id"), "audit_events", ["event_id"], unique=False)
    op.create_index(op.f("ix_audit_events_sequence_number"), "audit_events", ["sequence_number"], unique=False)
    op.create_index(op.f("ix_audit_events_run_id"), "audit_events", ["run_id"], unique=False)
    op.create_index(op.f("ix_audit_events_project_id"), "audit_events", ["project_id"], unique=False)
    op.create_index(op.f("ix_audit_events_event_type"), "audit_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_audit_events_current_event_hash"), "audit_events", ["current_event_hash"], unique=False)


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_column("verification_discrepancies", "confidence_score")
    op.drop_column("verification_discrepancies", "reason_code")
    op.drop_column("verification_discrepancies", "side_by_side")
    op.drop_column("verification_discrepancies", "assigned_at")
    op.drop_column("verification_discrepancies", "assigned_to")
    op.drop_column("verification_discrepancies", "cluster_name")
    op.drop_column("verification_discrepancies", "cluster_id")
    op.drop_column("verification_discrepancies", "resolved_at")
    op.drop_column("verification_discrepancies", "resolved_by")
    op.drop_column("verification_discrepancies", "resolution_note")
    op.drop_column("verification_discrepancies", "resolution_status")
    op.drop_column("verification_discrepancies", "severity")
    op.drop_column("verification_discrepancies", "currency")
    op.drop_column("verification_discrepancies", "exposure_amount")
    op.drop_column("verification_discrepancies", "variance_amount")
    op.drop_column("verification_discrepancies", "target_amount")
    op.drop_column("verification_discrepancies", "source_amount")
    op.drop_column("verification_discrepancies", "expected_amount")
    op.drop_column("verification_discrepancies", "aggregated_amount")
    op.drop_column("verification_discrepancies", "child_records")
    op.drop_column("verification_discrepancies", "source_records")
    op.drop_column("verification_discrepancies", "source_row_indices")
    op.drop_column("verification_runs", "sign_off_decided_at")
    op.drop_column("verification_runs", "sign_off_decision_note")
    op.drop_column("verification_runs", "sign_off_approved_by_name")
    op.drop_column("verification_runs", "sign_off_approved_by")
    op.drop_column("verification_runs", "sign_off_proposed_at")
    op.drop_column("verification_runs", "sign_off_proposal_note")
    op.drop_column("verification_runs", "sign_off_proposed_by_name")
    op.drop_column("verification_runs", "sign_off_proposed_by")
    op.drop_column("verification_runs", "sign_off_status")
    op.drop_column("verification_runs", "sources")
    op.drop_column("users", "role")
