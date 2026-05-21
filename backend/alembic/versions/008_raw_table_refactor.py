"""Refactor raw tables — drop ingested_at, add created_at, switch watermark to timestamp

Revision ID: 008
Revises: 007
Create Date: 2026-04-01

Raw tables are now treated as truly read-only source data. We no longer
stamp ingested_at after processing a row — that required write access to
tables we might not own in a real integration.

Instead:
  - Each raw table gains a created_at column (set by the DB on insert,
    simulating a system timestamp the source system would provide).
  - workers.ingestion_watermarks switches from last_id (INT) to
    last_seen_at (TIMESTAMPTZ). DAGs fetch WHERE created_at > last_seen_at
    and advance the watermark to MAX(created_at) of the batch.
  - An index on created_at is added to each raw table so the watermark
    filter is fast even on large tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Epoch default — ensures first DAG run fetches all existing rows without
# needing NULL handling in the WHERE clause.
_EPOCH = "1970-01-01 00:00:00+00"

_RAW_TABLES = [
    "crm_customers",
    "wms_inventory",
    "oms_transactions",
    "warehouse_stock",
]


def upgrade() -> None:
    for table in _RAW_TABLES:
        op.drop_column(table, "ingested_at", schema="raw")
        op.add_column(
            table,
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("NOW()"),
            ),
            schema="raw",
        )
        op.create_index(
            f"idx_raw_{table}_created_at",
            table,
            ["created_at"],
            schema="raw",
        )

    # Switch watermark from integer last_id to timestamp last_seen_at.
    op.drop_column("ingestion_watermarks", "last_id", schema="workers")
    op.add_column(
        "ingestion_watermarks",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text(f"'{_EPOCH}'::timestamptz"),
        ),
        schema="workers",
    )

    # ingestion_runs also tracked last_id — switch it to last_seen_at too
    # so run history is consistent with the watermark table.
    op.drop_column("ingestion_runs", "last_id", schema="workers")
    op.add_column(
        "ingestion_runs",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        schema="workers",
    )


def downgrade() -> None:
    op.drop_column("ingestion_runs", "last_seen_at", schema="workers")
    op.add_column(
        "ingestion_runs",
        sa.Column("last_id", sa.BigInteger, nullable=True),
        schema="workers",
    )

    op.drop_column("ingestion_watermarks", "last_seen_at", schema="workers")
    op.add_column(
        "ingestion_watermarks",
        sa.Column("last_id", sa.BigInteger, nullable=False, server_default="0"),
        schema="workers",
    )

    for table in _RAW_TABLES:
        op.drop_index(f"idx_raw_{table}_created_at", table_name=table, schema="raw")
        op.drop_column(table, "created_at", schema="raw")
        op.add_column(
            table,
            sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
            schema="raw",
        )
