"""
DAG: ingest_customers
Source:  raw.crm_customers       (unnormalized CRM export)
Target:  customers.customers     (normalized CRM table)

Transform steps:
  - Strip whitespace from full_name
  - Lowercase email_address → email
  - Expand territory short-codes (NE → Northeast, etc.) → region
  - Parse join_date text → TIMESTAMPTZ → created_at
  - Drop phone and account_tier (not part of our data model)

Idempotency: uses workers.ingestion_watermarks (last_raw_id) to fetch
only rows where id > last_raw_id each run. The watermark advances with
each committed batch so a mid-run failure leaves it pointing at the last
safe restart position.

Retry behaviour: start_run() is called at the top of load(), not extract().
Each task attempt — including Airflow retries — gets its own ingestion_runs
row. The failed partial run is preserved in the audit log and the retry row
shows only the remaining work.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook

from ingestion_utils import checkpoint_run, complete_run_in_tx, fail_run, finish_run, start_run

BATCH_SIZE = 50
# Non-zero in demo mode so the lock in simulate_offline.sh has time to fire.
# Set INGEST_BATCH_SLEEP=0 (or unset) for full-speed production runs.
BATCH_SLEEP = float(os.getenv("INGEST_BATCH_SLEEP", "0.5"))

SOURCE = "crm_customers"

TERRITORY_MAP = {
    "NE": "Northeast",
    "SE": "Southeast",
    "MW": "Midwest",
    "W": "West",
}


@dag(
    dag_id="ingest_customers",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "customers"],
    default_args={"retries": 3, "retry_delay": timedelta(seconds=30)},
)
def ingest_customers_dag() -> None:
    @task
    def extract() -> dict:
        hook = PostgresHook(postgres_conn_id="databridge_postgres")

        watermark = hook.get_first(
            "SELECT last_raw_id FROM workers.ingestion_watermarks WHERE source = %s",
            parameters=(SOURCE,),
        )
        last_raw_id = watermark[0] if watermark else 0

        total_available = hook.get_first(
            "SELECT COUNT(*) FROM raw.crm_customers WHERE id > %s",
            parameters=(last_raw_id,),
        )[0]
        rows = hook.get_records(
            """
            SELECT id, full_name, email_address, territory, join_date, created_at
            FROM raw.crm_customers
            WHERE id > %s
            ORDER BY id
            """,
            parameters=(last_raw_id,),
        )

        if len(rows) != total_available:
            raise RuntimeError(
                f"Extract mismatch for {SOURCE}: source has {total_available} rows, fetched {len(rows)}"
            )

        return {
            "last_raw_id": last_raw_id,
            "records": [
                {
                    "raw_id": row[0],
                    "full_name": row[1],
                    "email_address": row[2],
                    "territory": row[3],
                    "join_date": row[4],
                    "created_at": str(row[5]),
                }
                for row in rows
            ],
        }

    @task
    def transform(payload: dict) -> dict:
        records = payload["records"]
        normalized = [
            {
                "raw_id": r["raw_id"],
                "name": r["full_name"].strip(),
                "email": r["email_address"].lower().strip(),
                "region": TERRITORY_MAP.get(r["territory"].strip().upper(), r["territory"]),
                "created_at": r["join_date"].strip()[:19],
                "source_created_at": r["created_at"],
            }
            for r in records
        ]
        return {"last_raw_id": payload["last_raw_id"], "records": normalized}

    @task
    def load(payload: dict) -> None:
        hook = PostgresHook(postgres_conn_id="databridge_postgres")

        # Re-read the watermark at load time — on a retry, batches committed
        # during the previous attempt have already advanced it. Only process
        # records that weren't committed before.
        watermark = hook.get_first(
            "SELECT last_raw_id FROM workers.ingestion_watermarks WHERE source = %s",
            parameters=(SOURCE,),
        )
        current_last_raw_id = watermark[0] if watermark else 0
        records = [r for r in payload["records"] if r["raw_id"] > current_last_raw_id]

        if not records:
            print(f"No new records for {SOURCE} — watermark already current.")
            return

        # Each load attempt — first run or retry — gets its own ingestion_runs row.
        # The previous failed row is untouched; the audit log shows both.
        run_id = start_run(SOURCE, len(records))
        total_processed = 0
        try:
            for i in range(0, len(records), BATCH_SIZE):
                batch = records[i : i + BATCH_SIZE]
                is_last = i + BATCH_SIZE >= len(records)
                conn = hook.get_conn()
                cursor = conn.cursor()

                for r in batch:
                    cursor.execute(
                        """
                        INSERT INTO customers.customers (name, email, region, created_at)
                        VALUES (%(name)s, %(email)s, %(region)s, %(created_at)s)
                        ON CONFLICT (email) DO UPDATE
                            SET name   = EXCLUDED.name,
                                region = EXCLUDED.region
                        """,
                        r,
                    )

                batch_max_raw_id = max(r["raw_id"] for r in batch)
                batch_max_seen_at = max(r["source_created_at"] for r in batch)
                cursor.execute(
                    """
                    INSERT INTO workers.ingestion_watermarks (source, last_raw_id, last_seen_at, rows_processed, updated_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (source) DO UPDATE
                        SET last_raw_id    = EXCLUDED.last_raw_id,
                            last_seen_at   = EXCLUDED.last_seen_at,
                            rows_processed = ingestion_watermarks.rows_processed + EXCLUDED.rows_processed,
                            updated_at     = NOW()
                    """,
                    (SOURCE, batch_max_raw_id, batch_max_seen_at, len(batch)),
                )
                total_processed += len(batch)
                if is_last:
                    if total_processed != len(records):
                        raise RuntimeError(
                            f"Load mismatch for {SOURCE}: expected {len(records)}, wrote {total_processed}"
                        )
                    complete_run_in_tx(cursor, run_id, total_processed, 0, batch_max_seen_at)
                conn.commit()
                cursor.close()

                if not is_last:
                    checkpoint_run(run_id, total_processed)
                print(f"  committed batch {i // BATCH_SIZE + 1}: {total_processed}/{len(records)} rows, last_raw_id={batch_max_raw_id}")
                if BATCH_SLEEP:
                    time.sleep(BATCH_SLEEP)

            print(f"Loaded {total_processed} customers.")
        except Exception as e:
            fail_run(run_id, str(e))
            raise

    raw = extract()
    normalized = transform(raw)
    load(normalized)


ingest_customers_dag()
