"""Add resumed_from_id to workers.ingestion_runs

Links a retry run back to the failed run it continued from, so the audit
log makes clear that processed=1000 on a 1500-row source is not a partial
failure but a deliberate resume from a known watermark.

Revision ID: 012
Revises: 011
Create Date: 2026-04-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ingestion_runs",
        sa.Column("resumed_from_id", sa.Integer, sa.ForeignKey("workers.ingestion_runs.id"), nullable=True),
        schema="workers",
    )


def downgrade() -> None:
    op.drop_column("ingestion_runs", "resumed_from_id", schema="workers")
