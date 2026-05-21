"""Add workers.ingestion_watermarks for DAG watermark tracking

Revision ID: 007
Revises: 006
Create Date: 2026-04-01

Replaces the ingested_at IS NULL pattern on raw tables with a dedicated
watermark table. Each DAG reads last_id for its source, fetches only rows
with id > last_id, and advances the watermark after a successful load.

This mirrors what you'd do when reading from a source system you don't own
— you can't add an ingested_at column to their tables, so you track progress
on your side instead.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_watermarks",
        sa.Column("source", sa.String(100), primary_key=True),
        sa.Column("last_id", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("rows_processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        schema="workers",
    )


def downgrade() -> None:
    op.drop_table("ingestion_watermarks", schema="workers")
