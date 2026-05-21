"""
DAG: ingest_orders
Source:  raw.oms_transactions     (unnormalized OMS export)
Target:  sales.orders             (normalized orders table)

This DAG runs after ingest_customers and ingest_products because orders
reference customers and products by FK. Rows whose customer_email or item_code
can't be resolved are skipped — the watermark still advances past them since
the source system won't resend rows it already exported.

Transform steps:
  - customer_email    resolved to customers.customers.id via subquery
  - item_code         resolved to inventory.products.id via subquery
  - quantity_ordered  → quantity (rename)
  - sale_price        → unit_price (rename)
  - transaction_date  → ordered_at (text → timestamp parse)
  - payment_method    dropped
  - source_channel    dropped

Idempotency: uses workers.ingestion_watermarks (last_seen_at) to fetch
only rows where created_at > last_seen_at each run.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook

from ingestion_utils import checkpoint_run, complete_run_in_tx, fail_run, finish_run, start_run

BATCH_SIZE = 50

SOURCE = "oms_transactions"


@dag(
    dag_id="ingest_orders",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "orders"],
    default_args={"retries": 3, "retry_delay": timedelta(seconds=30)},
)
def ingest_orders_dag() -> None:
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
                "SELECT COUNT(*) FROM raw.oms_transactions WHERE id > %s",
                parameters=(last_raw_id,),
            )[0]
            rows = hook.get_records(
                """
                SELECT id, transaction_id, customer_email, item_code,
                       quantity_ordered, sale_price, transaction_date, created_at
                FROM raw.oms_transactions
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
                    "transaction_id": row[1],
                    "customer_email": row[2],
                    "item_code": row[3],
                    "quantity_ordered": row[4],
                    "sale_price": float(row[5]),
                    "transaction_date": row[6],
                    "created_at": str(row[7]),
                }
                for row in rows
            ],
        }

    @task
    def transform(payload: dict) -> dict:
        records = payload["records"]
        if not records:
            return {"last_raw_id": payload["last_raw_id"], "total_available": payload["total_available"], "skipped": 0, "records": [], "max_raw_id": payload["last_raw_id"]}

        hook = PostgresHook(postgres_conn_id="databridge_postgres")

        emails = list({r["customer_email"].lower().strip() for r in records})
        customer_rows = hook.get_records(
            "SELECT email, id FROM customers.customers WHERE email = ANY(%s)",
            parameters=(emails,),
        )
        customer_map = {row[0]: row[1] for row in customer_rows}

        skus = list({r["item_code"].strip().upper() for r in records})
        product_rows = hook.get_records(
            "SELECT sku, id FROM inventory.products WHERE sku = ANY(%s)",
            parameters=(skus,),
        )
        product_map = {row[0]: row[1] for row in product_rows}

        normalized = []
        skipped = 0
        for r in records:
            customer_id = customer_map.get(r["customer_email"].lower().strip())
            product_id = product_map.get(r["item_code"].strip().upper())

            if customer_id is None or product_id is None:
                skipped += 1
                continue

            normalized.append(
                {
                    "raw_id": r["raw_id"],
                    "customer_id": customer_id,
                    "product_id": product_id,
                    "quantity": r["quantity_ordered"],
                    "unit_price": r["sale_price"],
                    "ordered_at": r["transaction_date"].strip()[:19],
                    "source_created_at": r["created_at"],
                }
            )

        if skipped:
            print(f"Skipped {skipped} rows with unresolvable customer_email or item_code")

        max_raw_id = max(r["raw_id"] for r in records)
        return {"last_raw_id": payload["last_raw_id"], "total_available": payload["total_available"], "skipped": skipped, "records": normalized, "max_raw_id": max_raw_id}

    @task
    def load(payload: dict) -> None:
        hook = PostgresHook(postgres_conn_id="databridge_postgres")

        watermark = hook.get_first(
            "SELECT last_raw_id FROM workers.ingestion_watermarks WHERE source = %s",
            parameters=(SOURCE,),
        )
        current_last_raw_id = watermark[0] if watermark else 0
        records = [r for r in payload["records"] if r["raw_id"] > current_last_raw_id]
        skipped = payload["skipped"]

        if not records and payload["max_raw_id"] <= current_last_raw_id:
            print(f"No new records for {SOURCE} — watermark already current.")
            return

        run_id = start_run(SOURCE, len(records) + skipped)
        total_processed = 0
        batch_max_raw_id = current_last_raw_id
        try:

            for i in range(0, len(records), BATCH_SIZE):
                batch = records[i : i + BATCH_SIZE]
                is_last = i + BATCH_SIZE >= len(records)
                conn = hook.get_conn()
                cursor = conn.cursor()

                for r in batch:
                    cursor.execute(
                        """
                        INSERT INTO sales.orders
                            (customer_id, product_id, quantity, unit_price, ordered_at)
                        VALUES
                            (%(customer_id)s, %(product_id)s, %(quantity)s, %(unit_price)s, %(ordered_at)s)
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
                    expected = len(records) + skipped
                    if total_processed + skipped != expected:
                        raise RuntimeError(
                            f"Load mismatch for {SOURCE}: expected {expected}, "
                            f"wrote {total_processed}, skipped {skipped}"
                        )
                    complete_run_in_tx(cursor, run_id, total_processed, skipped, batch_max_seen_at)
                conn.commit()
                cursor.close()

                if not is_last:
                    checkpoint_run(run_id, total_processed)
                print(f"  committed batch {i // BATCH_SIZE + 1}: {total_processed}/{len(records)} rows, last_raw_id={batch_max_raw_id}")

            print(f"Loaded {total_processed} orders, skipped {skipped}.")
        except Exception as e:
            fail_run(run_id, str(e))
            raise

    raw = extract()
    normalized = transform(raw)
    load(normalized)


ingest_orders_dag()
