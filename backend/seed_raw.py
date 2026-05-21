"""
Populates the raw landing-zone tables with unnormalized source data.

This is the intended starting point for the demo — seed here, then let
Airflow do the work of normalizing and loading the target tables.
seed.py (which seeds the normalized tables directly) exists for quick
local dev only; for any demo of the ETL pipeline, use this script instead.

This simulates what a real integration would receive: a daily dump from a CRM,
WMS, and OMS — each with their own column names, date formats, and extra fields
that need to be cleaned up before they reach the normalized tables.

Run after `docker compose up`:
    docker compose exec backend python seed_raw.py

Then trigger the Airflow DAGs at http://localhost:8080:
    ingest_customers → ingest_products → ingest_orders
"""

import random
from datetime import UTC, datetime, timedelta

import psycopg2
from faker import Faker

from core.config import settings

fake = Faker()
Faker.seed(99)
random.seed(99)

TERRITORY_CODES = ["NE", "SE", "MW", "W"]

# WMS uses slightly different category names to the ones in inventory.products
# — kept identical here so the transform step doesn't need a mapping,
# but the column rename (department → category) and type coercions are still
# demonstrated by the other fields.
WMS_DEPARTMENTS = ["Electronics", "Office", "Supplies"]

PAYMENT_METHODS = ["credit_card", "debit_card", "purchase_order", "wire_transfer"]
SOURCE_CHANNELS = ["web", "mobile", "phone", "partner_api"]
ACCOUNT_TIERS = ["Bronze", "Silver", "Gold"]

STORES = [
    ("Boston Flagship", "Boston", "Northeast"),
    ("New York Downtown", "New York", "Northeast"),
    ("Philadelphia Hub", "Philadelphia", "Northeast"),
    ("Atlanta Central", "Atlanta", "Southeast"),
    ("Miami Beach", "Miami", "Southeast"),
    ("Chicago Loop", "Chicago", "Midwest"),
    ("Detroit Metro", "Detroit", "Midwest"),
    ("Los Angeles Main", "Los Angeles", "West"),
    ("San Francisco Bay", "San Francisco", "West"),
    ("Seattle Center", "Seattle", "West"),
]


def random_past_date(days_back: int = 730) -> str:
    """Return an ISO datetime string in the past, as a raw text value."""
    dt = datetime.now(tz=UTC) - timedelta(
        days=random.randint(0, days_back),  # noqa: S311
        hours=random.randint(0, 23),  # noqa: S311
        minutes=random.randint(0, 59),  # noqa: S311
    )
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def seed_crm_customers(cursor: psycopg2.extensions.cursor, n: int = 30) -> list[str]:
    """Insert raw CRM customer records. Returns list of inserted emails."""
    emails = []
    for _ in range(n):
        email = fake.unique.email()
        cursor.execute(
            """
            INSERT INTO raw.crm_customers
                (full_name, email_address, territory, join_date, phone, account_tier)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                fake.name(),
                email,
                random.choice(TERRITORY_CODES),  # noqa: S311
                random_past_date(730),
                fake.phone_number()[:30],
                random.choice(ACCOUNT_TIERS),  # noqa: S311
            ),
        )
        emails.append(email)
    return emails


def seed_wms_inventory(cursor: psycopg2.extensions.cursor, n: int = 10) -> list[str]:
    """Insert raw WMS product records. Returns list of inserted item_codes."""
    item_codes = []
    base = 100  # start above existing SKU-0001..SKU-0015 range
    for i in range(n):
        item_code = f"SKU-{base + i:04d}"
        reorder_point = random.randint(10, 60)  # noqa: S311
        # ~30% chance a product is low or out of stock
        if random.random() < 0.3:  # noqa: S311
            quantity_on_hand = random.randint(0, reorder_point - 1)  # noqa: S311
        else:
            quantity_on_hand = random.randint(reorder_point, 500)  # noqa: S311

        cursor.execute(
            """
            INSERT INTO raw.wms_inventory
                (item_code, item_name, department, quantity_on_hand,
                 reorder_point, cost_price, warehouse_bin, last_sync)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                item_code,
                fake.catch_phrase()[:80],
                random.choice(WMS_DEPARTMENTS),  # noqa: S311
                quantity_on_hand,
                reorder_point,
                round(random.uniform(5.0, 200.0), 2),  # noqa: S311
                f"AISLE-{random.randint(1, 20)}-BIN-{random.randint(1, 50):02d}",  # noqa: S311
                random_past_date(30),
            ),
        )
        item_codes.append(item_code)
    return item_codes


def seed_oms_transactions(
    cursor: psycopg2.extensions.cursor,
    customer_emails: list[str],
    item_codes: list[str],
    n: int = 60,
) -> None:
    """Insert raw OMS transaction records."""
    for _ in range(n):
        cursor.execute(
            """
            INSERT INTO raw.oms_transactions
                (transaction_id, customer_email, item_code, quantity_ordered,
                 sale_price, transaction_date, payment_method, source_channel)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (transaction_id) DO NOTHING
            """,
            (
                fake.uuid4(),
                random.choice(customer_emails),  # noqa: S311
                random.choice(item_codes),  # noqa: S311
                random.randint(1, 20),  # noqa: S311
                round(random.uniform(9.99, 499.99), 2),  # noqa: S311
                random_past_date(365),
                random.choice(PAYMENT_METHODS),  # noqa: S311
                random.choice(SOURCE_CHANNELS),  # noqa: S311
            ),
        )


def seed_warehouse_stock(
    cursor: psycopg2.extensions.cursor,
    item_codes: list[str],
) -> int:
    """Insert one row per store+product into raw.warehouse_stock.

    Uses the same item_codes that were just inserted into raw.wms_inventory
    so the ingest_warehouse_stock DAG can resolve them by SKU after
    ingest_products has run.
    """
    product_names = {f"SKU-{100 + i:04d}": fake.catch_phrase()[:80] for i in range(len(item_codes))}
    departments = ["Electronics", "Office", "Supplies"]
    count = 0

    for store_name, store_city, store_region in STORES:
        for item_code in item_codes:
            reorder_level = random.randint(10, 40)  # noqa: S311
            # ~30% chance a store is low/out of stock on any given product
            if random.random() < 0.3:  # noqa: S311
                qty = random.randint(0, reorder_level - 1)  # noqa: S311
            else:
                qty = random.randint(reorder_level, 300)  # noqa: S311

            cursor.execute(
                """
                INSERT INTO raw.warehouse_stock
                    (store_name, store_city, store_region, product_sku,
                     product_name, category, qty_on_hand, reorder_level, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    store_name,
                    store_city,
                    store_region,
                    item_code,
                    product_names[item_code],
                    random.choice(departments),  # noqa: S311
                    qty,
                    reorder_level,
                    random_past_date(7),
                ),
            )
            count += 1

    return count


def main() -> None:
    conn = psycopg2.connect(settings.database_url.replace("+psycopg2", ""))
    cursor = conn.cursor()

    # Truncate all raw tables and reset watermarks so re-running gives a clean slate.
    # Raw tables are treated as read-only source data — we never update rows in place.
    cursor.execute("TRUNCATE raw.warehouse_stock, raw.oms_transactions, raw.wms_inventory, raw.crm_customers")
    cursor.execute("TRUNCATE workers.ingestion_watermarks")
    fake.unique.clear()

    print("Seeding raw.crm_customers …")
    emails = seed_crm_customers(cursor, n=200)

    print("Seeding raw.wms_inventory …")
    item_codes = seed_wms_inventory(cursor, n=15)

    print("Seeding raw.oms_transactions …")
    seed_oms_transactions(cursor, emails, item_codes, n=500)

    print("Seeding raw.warehouse_stock …")
    stock_count = seed_warehouse_stock(cursor, item_codes)

    conn.commit()
    cursor.close()
    conn.close()

    print(
        f"\nDone. Raw tables populated:\n"
        f"  raw.crm_customers     → {len(emails)} rows\n"
        f"  raw.wms_inventory     → {len(item_codes)} rows\n"
        f"  raw.oms_transactions  → 500 rows\n"
        f"  raw.warehouse_stock   → {stock_count} rows ({len(STORES)} stores × {len(item_codes)} products)\n"  # noqa: RUF001
        f"\nRun the Airflow DAGs at http://localhost:8080 to ingest these into\n"
        f"the normalized tables (customers, inventory, sales schemas).\n"
        f"  DAGs: ingest_customers → ingest_products → ingest_orders → ingest_warehouse_stock\n"
    )


if __name__ == "__main__":
    main()
