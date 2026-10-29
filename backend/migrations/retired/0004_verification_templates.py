"""Create verification_templates table (REUSABLE TEMPLATE FEATURE)

Batch 11 implementation. Review docs/REUSABLE_VERIFICATION_TEMPLATES_DESIGN.md
(§2, §7) for the design rationale.

Application status (Batch 12): APPLIED to the local development database
(`verifygrid` @ localhost, revision `0003_user_password` -> head) after a
read-only review confirmed the target's history matches this repository's
migration graph. The `.env`-configured cloud database has a divergent,
unrelated migration history (`0004_enterprise_governance`) and was NOT touched.

Revision ID: 0004_verification_templates
Revises: 0003_user_password
Create Date: 2026-10-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_verification_templates"
down_revision: Union[str, None] = "0003_user_password"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "verification_templates",
        # Stable template ID (same UUID convention as projects/verification_runs).
        sa.Column("id", sa.Uuid(), nullable=False),
        # Tenant ownership: mirrors projects.owner_id (SET NULL on user deletion).
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # 'organization' | 'financial' — enforced at the application boundary.
        sa.Column("mode", sa.String(length=50), nullable=False),
        # 'personal' | 'organization_shared' (dormant until Organizations exist).
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="personal"),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        # Versioned, validated configuration snapshot (see design doc §3).
        sa.Column("configuration", sa.JSON(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("owner_id", "name", name="uq_verification_templates_owner_name"),
    )
    op.create_index(
        "ix_verification_templates_owner_id",
        "verification_templates",
        ["owner_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_verification_templates_owner_id", table_name="verification_templates")
    op.drop_table("verification_templates")
