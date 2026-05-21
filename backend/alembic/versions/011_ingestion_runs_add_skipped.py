"""Add skipped column to workers.ingestion_runs

Revision ID: 011
Revises: 010
Create Date: 2026-04-04

A run is only truly complete if processed + skipped == total.
Without tracking skipped rows, silently dropped records (unresolvable FKs,
transform errors) are invisible in the audit log.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ingestion_runs",
        sa.Column("skipped", sa.Integer, nullable=False, server_default="0"),
        schema="workers",
    )


def downgrade() -> None:
    op.drop_column("ingestion_runs", "skipped", schema="workers")
