"""Add multi-source and aggregation lineage columns

Batch 16 migration-parity repair.

The SQLAlchemy models have required these six columns since the multi-source
and aggregation batches, but the committed migration graph stopped at
``0004_verification_templates``. A database built from that graph could not
persist or read multi-source lineage, and could not persist split-payment
aggregation lineage.

All six fields are nullable by design:

- Legacy single-source runs have no per-run ``sources`` snapshot.
- Legacy discrepancies have no per-source row/record lineage.
- Non-aggregation discrepancies have no child records or amounts.
- NULL therefore means "not recorded for this row", not missing data that can
  be reconstructed. No backfill is appropriate.

Each added column is nullable and has no server default, so PostgreSQL can add
it without rewriting existing rows. No indexes or foreign keys are added:
these are opaque lineage snapshots, not query or join keys.

Revision ID: 0005_verification_lineage
Revises: 0004_verification_templates
Create Date: 2026-10-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005_verification_lineage"
down_revision: Union[str, None] = "0004_verification_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Per-run source snapshot used by persistent multi-source runs.
    op.add_column(
        "verification_runs",
        sa.Column("sources", sa.JSON(), nullable=True),
    )

    # Per-discrepancy multi-source lineage. JSON preserves the alias-keyed
    # row-index and record maps without imposing a relational shape on them.
    op.add_column(
        "verification_discrepancies",
        sa.Column("source_row_indices", sa.JSON(), nullable=True),
    )
    op.add_column(
        "verification_discrepancies",
        sa.Column("source_records", sa.JSON(), nullable=True),
    )

    # Split-payment aggregation lineage and amounts. Float matches the ORM's
    # ``Float`` type and PostgreSQL's double-precision representation.
    op.add_column(
        "verification_discrepancies",
        sa.Column("child_records", sa.JSON(), nullable=True),
    )
    op.add_column(
        "verification_discrepancies",
        sa.Column("aggregated_amount", sa.Float(), nullable=True),
    )
    op.add_column(
        "verification_discrepancies",
        sa.Column("expected_amount", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    # Dropping these columns discards lineage that did not exist before this
    # revision. Base run and discrepancy rows are preserved.
    op.drop_column("verification_discrepancies", "expected_amount")
    op.drop_column("verification_discrepancies", "aggregated_amount")
    op.drop_column("verification_discrepancies", "child_records")
    op.drop_column("verification_discrepancies", "source_records")
    op.drop_column("verification_discrepancies", "source_row_indices")
    op.drop_column("verification_runs", "sources")
