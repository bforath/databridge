"""
Shared helpers for ingestion DAGs.

Writes run history to workers.ingestion_runs so there's a full audit log
of every DAG execution alongside the moving watermark in ingestion_watermarks.
"""

from __future__ import annotations

from airflow.providers.postgres.hooks.postgres import PostgresHook


def start_run(source: str, total: int) -> int:
    """Insert a new ingestion_runs row and return its id.

    Any previous runs for this source that are still marked 'running' are
    closed out as crashed before the new run is recorded. This handles the
    case where a worker was killed externally (pg_terminate_backend, OOM,
    container restart) and couldn't write its own fail_run() update.

    If the most recent run for this source failed, the new row is linked to
    it via resumed_from_id so the audit log makes clear that this run is a
    continuation rather than an independent attempt.
    """
    hook = PostgresHook(postgres_conn_id="databridge_postgres")
    conn = hook.get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE workers.ingestion_runs
        SET status      = 'failed',
            message     = 'process killed',
            finished_at = NOW()
        WHERE source = %s AND status = 'running'
        """,
        (source,),
    )
    cursor.execute(
        """
        SELECT id FROM workers.ingestion_runs
        WHERE source = %s AND status = 'failed'
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (source,),
    )
    row = cursor.fetchone()
    resumed_from_id = row[0] if row else None

    cursor.execute(
        """
        INSERT INTO workers.ingestion_runs (source, total, processed, status, started_at, resumed_from_id)
        VALUES (%s, %s, 0, 'running', NOW(), %s)
        RETURNING id
        """,
        (source, total, resumed_from_id),
    )
    run_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    return run_id


def finish_run(run_id: int, processed: int, last_seen_at: str) -> None:
    """Mark a run as complete with final row count and watermark timestamp."""
    hook = PostgresHook(postgres_conn_id="databridge_postgres")
    conn = hook.get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE workers.ingestion_runs
        SET processed    = %s,
            last_seen_at = %s,
            status       = 'complete',
            finished_at  = NOW()
        WHERE id = %s
        """,
        (processed, last_seen_at, run_id),
    )
    conn.commit()
    cursor.close()


def complete_run_in_tx(cursor, run_id: int, processed: int, skipped: int, last_seen_at: str) -> None:
    """Write the 'complete' status using an already-open cursor.

    Call this before conn.commit() on the final batch so the run completion
    and the last watermark advance are in the same transaction. If the process
    dies after commit, the run is complete. If it dies before, everything
    rolls back and start_run()'s sweep will close it as 'failed: process killed'.
    """
    cursor.execute(
        """
        UPDATE workers.ingestion_runs
        SET processed    = %s,
            skipped      = %s,
            last_seen_at = %s,
            status       = 'complete',
            finished_at  = NOW()
        WHERE id = %s
        """,
        (processed, skipped, last_seen_at, run_id),
    )


def checkpoint_run(run_id: int, processed: int) -> None:
    """Update the live processed count after each committed batch."""
    hook = PostgresHook(postgres_conn_id="databridge_postgres")
    conn = hook.get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE workers.ingestion_runs SET processed = %s WHERE id = %s",
        (processed, run_id),
    )
    conn.commit()
    cursor.close()


def fail_run(run_id: int, error: str) -> None:
    """Mark a run as failed with the error detail in the message column."""
    hook = PostgresHook(postgres_conn_id="databridge_postgres")
    conn = hook.get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE workers.ingestion_runs
        SET status      = 'failed',
            message     = %s,
            finished_at = NOW()
        WHERE id = %s
        """,
        (error[:500], run_id),
    )
    conn.commit()
    cursor.close()
