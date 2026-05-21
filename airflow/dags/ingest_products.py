"""
DAG: ingest_products
Source:  raw.wms_inventory        (unnormalized WMS export)
Target:  inventory.products       (normalized inventory table)

Transform steps:
  - item_code          → sku  (rename)
  - item_name          → name (rename + strip)
  - department         → category (rename)
  - quantity_on_hand   → stock_qty (rename)
  - reorder_point      → reorder_level (rename)
  - cost_price         dropped (WMS-internal)
  - warehouse_bin      dropped (WMS-internal)
  - last_sync          dropped

Idempotency: uses workers.ingestion_watermarks (last_seen_at) to fetch
only rows where created_at > last_seen_at each run.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook

from ingestion_utils import checkpoint_run, complete_run_in_tx, fail_run, finish_run, start_run

BATCH_SIZE = 50

SOURCE = "wms_inventory"


@dag(
    dag_id="ingest_products",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "products"],
    default_args={"retries": 3, "retry_delay": timedelta(seconds=30)},
)
def ingest_products_dag() -> None:
    @task
    def extract() -> dict:
        hook = PostgresHook(postgres_conn_id="databridge_postgres")

        watermark = hook.get_first(
            "SELECT last_raw_id FROM workers.ingestion_watermarks WHERE source = %s",
            parameters=(SOURCE,),
        )
        last_raw_id = watermark[0] if watermark else 0

        try:
            total_available = hook.get_first(
                "SELECT COUNT(*) FROM raw.wms_inventory WHERE id > %s",
                parameters=(last_raw_id,),
            )[0]
            rows = hook.get_records(
                """
                SELECT id, item_code, item_name, department, quantity_on_hand, reorder_point, created_at
                FROM raw.wms_inventory
                WHERE id > %s
                ORDER BY id
                """,
                parameters=(last_raw_id,),
            )
        except Exception as e:
            raise

        if len(rows) != total_available:
            raise RuntimeError(
                f"Extract mismatch for {SOURCE}: source has {total_available} rows, fetched {len(rows)}"
            )

        return {
            "last_raw_id": last_raw_id,
            "total_available": total_available,
            "records": [
                {
                    "raw_id": row[0],
                    "item_code": row[1],
                    "item_name": row[2],
                    "department": row[3],
                    "quantity_on_hand": row[4],
                    "reorder_point": row[5],
                    "created_at": str(row[6]),
                }
                for row in rows
            ],
        }

    @task
    def transform(payload: dict) -> dict:
        return {
            "last_raw_id": payload["last_raw_id"],
            "total_available": payload["total_available"],
            "records": [
                {
                    "raw_id": r["raw_id"],
                    "sku": r["item_code"].strip().upper(),
                    "name": r["item_name"].strip(),
                    "category": r["department"].strip(),
                    "stock_qty": max(0, r["quantity_on_hand"]),
                    "reorder_level": r["reorder_point"],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "source_created_at": r["created_at"],
                }
                for r in payload["records"]
            ],
        }

    @task
    def load(payload: dict) -> None:
        hook = PostgresHook(postgres_conn_id="databridge_postgres")

        watermark = hook.get_first(
            "SELECT last_raw_id FROM workers.ingestion_watermarks WHERE source = %s",
            parameters=(SOURCE,),
        )
        current_last_raw_id = watermark[0] if watermark else 0
        records = [r for r in payload["records"] if r["raw_id"] > current_last_raw_id]

        if not records:
            print(f"No new records for {SOURCE} — watermark already current.")
            return

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
                        INSERT INTO inventory.products (sku, name, category, stock_qty, reorder_level, updated_at)
                        VALUES (%(sku)s, %(name)s, %(category)s, %(stock_qty)s, %(reorder_level)s, %(updated_at)s)
                        ON CONFLICT (sku) DO UPDATE
                            SET name          = EXCLUDED.name,
                                category      = EXCLUDED.category,
                                stock_qty     = EXCLUDED.stock_qty,
                                reorder_level = EXCLUDED.reorder_level,
                                updated_at    = NOW()
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

            print(f"Loaded {total_processed} products.")
        except Exception as e:
            fail_run(run_id, str(e))
            raise

    raw = extract()
    normalized = transform(raw)
    load(normalized)


ingest_products_dag()
