"""Split status + message in workers.ingestion_runs

Separates the error detail out of the status column into a dedicated
message column so status is always a clean label ("running", "complete",
"failed") and message carries the optional detail text.

Existing rows with status like "failed: process killed" are migrated:
  status  → "failed"
  message → everything after the first ": "

Revision ID: 013
Revises: 012
Create Date: 2026-04-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ingestion_runs",
        sa.Column("message", sa.Text, nullable=True),
        schema="workers",
    )
    # Migrate existing combined values: "failed: <detail>" → status="failed", message="<detail>"
    op.execute("""
        UPDATE workers.ingestion_runs
        SET message = TRIM(SUBSTRING(status FROM POSITION(': ' IN status) + 2)),
            status  = 'failed'
        WHERE status LIKE 'failed: %'
    """)
    # Widen status back to a short clean label — previous max was 255 after migration 010.
    # Keep at 50 characters; labels are "running", "complete", "failed".
    op.alter_column(
        "ingestion_runs", "status",
        type_=sa.String(50),
        schema="workers",
    )


def downgrade() -> None:
    op.execute("""
        UPDATE workers.ingestion_runs
        SET status = 'failed: ' || COALESCE(message, '')
        WHERE status = 'failed' AND message IS NOT NULL
    """)
    op.alter_column(
        "ingestion_runs", "status",
        type_=sa.String(255),
        schema="workers",
    )
    op.drop_column("ingestion_runs", "message", schema="workers")
