"""
DAG: ingest_warehouse_stock
Source:  raw.warehouse_stock      (denormalized store+product dump)
Target:  stores.locations         (normalized store records)
         stores.stock             (store-level inventory per product)

The raw table has one flat row per store+product combination — store name,
city, region, and product details all embedded together. This DAG splits
that into two normalized tables and resolves product FKs by SKU.

Transform steps:
  - Deduplicate store_name → upsert into stores.locations
  - product_sku resolved to inventory.products.id
  - qty_on_hand + reorder_level kept per store (not global defaults)
  - last_updated (text) parsed to timestamp for updated_at

Idempotency: uses workers.ingestion_watermarks (last_seen_at) to fetch
only rows where created_at > last_seen_at each run.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook

from ingestion_utils import checkpoint_run, complete_run_in_tx, fail_run, finish_run, start_run

BATCH_SIZE = 50

SOURCE = "warehouse_stock"


@dag(
    dag_id="ingest_warehouse_stock",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "stores"],
    default_args={"retries": 3, "retry_delay": timedelta(seconds=30)},
)
def ingest_warehouse_stock_dag() -> None:
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
                "SELECT COUNT(*) FROM raw.warehouse_stock WHERE id > %s",
                parameters=(last_raw_id,),
            )[0]
            rows = hook.get_records(
                """
                SELECT id, store_name, store_city, store_region,
                       product_sku, qty_on_hand, reorder_level, last_updated, created_at
                FROM raw.warehouse_stock
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
                    "store_name": row[1],
                    "store_city": row[2],
                    "store_region": row[3],
                    "product_sku": row[4],
                    "qty_on_hand": row[5],
                    "reorder_level": row[6],
                    "last_updated": row[7],
                    "created_at": str(row[8]),
                }
                for row in rows
            ],
        }

    @task
    def transform(payload: dict) -> dict:
        records = payload["records"]
        if not records:
            return {"last_raw_id": payload["last_raw_id"], "total_available": payload["total_available"], "skipped": 0, "stores": [], "stock": [], "max_raw_id": payload["last_raw_id"]}

        hook = PostgresHook(postgres_conn_id="databridge_postgres")

        skus = list({r["product_sku"].strip().upper() for r in records})
        product_rows = hook.get_records(
            "SELECT sku, id FROM inventory.products WHERE sku = ANY(%s)",
            parameters=(skus,),
        )
        product_map = {row[0]: row[1] for row in product_rows}

        store_map: dict[str, dict] = {}
        for r in records:
            name = r["store_name"].strip()
            store_map[name] = {
                "name": name,
                "city": r["store_city"].strip(),
                "region": r["store_region"].strip(),
            }

        now = datetime.now(timezone.utc).isoformat()
        stock_rows = []
        skipped = 0
        for r in records:
            product_id = product_map.get(r["product_sku"].strip().upper())
            if product_id is None:
                skipped += 1
                continue
            stock_rows.append(
                {
                    "raw_id": r["raw_id"],
                    "store_name": r["store_name"].strip(),
                    "product_id": product_id,
                    "qty_on_hand": max(0, r["qty_on_hand"]),
                    "reorder_level": r["reorder_level"],
                    "updated_at": now,
                    "source_created_at": r["created_at"],
                }
            )

        if skipped:
            print(f"Skipped {skipped} rows with unresolvable product_sku")

        max_raw_id = max(r["raw_id"] for r in records)
        return {
            "last_raw_id": payload["last_raw_id"],
            "total_available": payload["total_available"],
            "skipped": skipped,
            "stores": list(store_map.values()),
            "stock": stock_rows,
            "max_raw_id": max_raw_id,
        }

    @task
    def load(payload: dict) -> None:
        hook = PostgresHook(postgres_conn_id="databridge_postgres")

        watermark = hook.get_first(
            "SELECT last_raw_id FROM workers.ingestion_watermarks WHERE source = %s",
            parameters=(SOURCE,),
        )
        current_last_raw_id = watermark[0] if watermark else 0

        stores = payload.get("stores", [])
        all_stock = payload.get("stock", [])
        stock_rows = [r for r in all_stock if r["raw_id"] > current_last_raw_id]
        skipped = payload["skipped"]

        if not stock_rows and payload["max_raw_id"] <= current_last_raw_id:
            print(f"No new records for {SOURCE} — watermark already current.")
            return

        run_id = start_run(SOURCE, len(stock_rows) + skipped)
        total_processed = 0
        batch_max_raw_id = current_last_raw_id
        try:
            now = datetime.now(timezone.utc).isoformat()

            # Upsert all stores first (no batching needed — deduped already)
            conn = hook.get_conn()
            cursor = conn.cursor()
            store_id_map: dict[str, int] = {}
            for s in stores:
                cursor.execute(
                    """
                    INSERT INTO stores.locations (name, city, region, created_at)
                    VALUES (%(name)s, %(city)s, %(region)s, %(now)s)
                    ON CONFLICT (name) DO UPDATE
                        SET city   = EXCLUDED.city,
                            region = EXCLUDED.region
                    RETURNING id
                    """,
                    {**s, "now": now},
                )
                store_id_map[s["name"]] = cursor.fetchone()[0]
            conn.commit()
            cursor.close()

            for i in range(0, len(stock_rows), BATCH_SIZE):
                batch = stock_rows[i : i + BATCH_SIZE]
                is_last = i + BATCH_SIZE >= len(stock_rows)
                conn = hook.get_conn()
                cursor = conn.cursor()

                for r in batch:
                    store_id = store_id_map.get(r["store_name"])
                    if store_id is None:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO stores.stock
                            (store_id, product_id, qty_on_hand, reorder_level, updated_at)
                        VALUES (%(store_id)s, %(product_id)s, %(qty_on_hand)s, %(reorder_level)s, %(updated_at)s)
                        ON CONFLICT (store_id, product_id) DO UPDATE
                            SET qty_on_hand   = EXCLUDED.qty_on_hand,
                                reorder_level = EXCLUDED.reorder_level,
                                updated_at    = EXCLUDED.updated_at
                        """,
                        {**r, "store_id": store_id},
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
                    expected = len(stock_rows) + skipped
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
                print(f"  committed batch {i // BATCH_SIZE + 1}: {total_processed}/{len(stock_rows)} rows, last_raw_id={batch_max_raw_id}")

            print(f"Loaded {total_processed} stock rows, skipped {skipped}.")
        except Exception as e:
            fail_run(run_id, str(e))
            raise

    raw = extract()
    transformed = transform(raw)
    load(transformed)


ingest_warehouse_stock_dag()
