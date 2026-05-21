"""Widen workers.ingestion_runs.status from VARCHAR(20) to VARCHAR(255)

Revision ID: 010
Revises: 009
Create Date: 2026-04-04

VARCHAR(20) was too short to hold failure messages like "failed: <error>"
which are written by fail_run() and the new process-killed recovery path.
Any status longer than 20 chars was silently truncated or raised an error,
meaning failed runs could appear to stay in 'running' state indefinitely.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "ingestion_runs",
        "status",
        existing_type=sa.String(20),
        type_=sa.String(255),
        schema="workers",
    )


def downgrade() -> None:
    op.alter_column(
        "ingestion_runs",
        "status",
        existing_type=sa.String(255),
        type_=sa.String(20),
        schema="workers",
    )
