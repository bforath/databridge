"""Add last_raw_id to workers.ingestion_watermarks for reliable resumption

Revision ID: 009
Revises: 008
Create Date: 2026-04-04

Timestamp-based watermarks (last_seen_at) break when multiple source rows
share the same created_at value — a common outcome of bulk inserts. After
committing a batch whose max timestamp equals N rows that weren't yet
processed, the next run's WHERE created_at > last_seen_at skips them.

last_raw_id (the source table's serial PK) is strictly monotonic and has
no ties. Switching the extract filter to WHERE id > last_raw_id ORDER BY id
guarantees exact resumption regardless of timestamp distribution.

last_seen_at is kept for human-readable history in ingestion_runs.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ingestion_watermarks",
        sa.Column("last_raw_id", sa.BigInteger, nullable=False, server_default="0"),
        schema="workers",
    )


def downgrade() -> None:
    op.drop_column("ingestion_watermarks", "last_raw_id", schema="workers")
