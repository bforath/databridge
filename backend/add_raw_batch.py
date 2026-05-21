"""
Appends a fresh batch of raw rows to simulate a daily source-system dump.

Unlike seed_raw.py (which truncates and reseeds), this script only INSERTs —
raw tables are left intact and the watermark is NOT reset. The new rows get
created_at = NOW(), so they appear after whatever the current watermark is.
Run multiple times to build up multiple days of data before or between DAG runs.

Usage:
    docker compose exec backend python add_raw_batch.py
    docker compose exec backend python add_raw_batch.py --customers 50 --products 5 --orders 150
"""

from __future__ import annotations

import argparse
import random
import time
from datetime import UTC, datetime, timedelta

import psycopg2
from faker import Faker

from core.config import settings

TERRITORY_CODES = ["NE", "SE", "MW", "W"]
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


def _fake_and_seed() -> Faker:
    """Return a Faker instance seeded from the current time so each batch produces unique data."""
    seed = int(time.time() * 1000) % (2**31)
    fake = Faker()
    Faker.seed(seed)
    random.seed(seed)
    return fake


def _next_sku_base(cursor: psycopg2.extensions.cursor) -> int:
    """Find the highest numeric suffix already in raw.wms_inventory to avoid collisions."""
    cursor.execute("SELECT item_code FROM raw.wms_inventory WHERE item_code ~ '^SKU-[0-9]+$'")
    codes = [row[0] for row in cursor.fetchall()]
    if not codes:
        return 1000
    nums = [int(c.split("-")[1]) for c in codes]
    return max(nums) + 1


def _transaction_date() -> str:
    """ISO timestamp within the past 24 hours — simulates today's orders."""
    dt = datetime.now(tz=UTC) - timedelta(
        hours=random.randint(0, 23),  # noqa: S311
        minutes=random.randint(0, 59),  # noqa: S311
    )
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def add_customers(cursor: psycopg2.extensions.cursor, fake: Faker, n: int) -> list[str]:
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
                _transaction_date(),
                fake.phone_number()[:30],
                random.choice(ACCOUNT_TIERS),  # noqa: S311
            ),
        )
        emails.append(email)
    return emails


def add_products(cursor: psycopg2.extensions.cursor, fake: Faker, n: int, sku_base: int) -> list[str]:
    item_codes = []
    for i in range(n):
        item_code = f"SKU-{sku_base + i:04d}"
        reorder_point = random.randint(10, 60)  # noqa: S311
        qty = (
            random.randint(0, reorder_point - 1)  # noqa: S311
            if random.random() < 0.3  # noqa: S311
            else random.randint(reorder_point, 500)  # noqa: S311
        )
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
                qty,
                reorder_point,
                round(random.uniform(5.0, 200.0), 2),  # noqa: S311
                f"AISLE-{random.randint(1, 20)}-BIN-{random.randint(1, 50):02d}",  # noqa: S311
                _transaction_date(),
            ),
        )
        item_codes.append(item_code)
    return item_codes


def add_orders(
    cursor: psycopg2.extensions.cursor,
    fake: Faker,
    emails: list[str],
    item_codes: list[str],
    n: int,
) -> None:
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
                random.choice(emails),  # noqa: S311
                random.choice(item_codes),  # noqa: S311
                random.randint(1, 20),  # noqa: S311
                round(random.uniform(9.99, 499.99), 2),  # noqa: S311
                _transaction_date(),
                random.choice(PAYMENT_METHODS),  # noqa: S311
                random.choice(SOURCE_CHANNELS),  # noqa: S311
            ),
        )


def add_warehouse_stock(
    cursor: psycopg2.extensions.cursor,
    fake: Faker,
    item_codes: list[str],
) -> int:
    count = 0
    for store_name, store_city, store_region in STORES:
        for item_code in item_codes:
            reorder_level = random.randint(10, 40)  # noqa: S311
            qty = (
                random.randint(0, reorder_level - 1)  # noqa: S311
                if random.random() < 0.3  # noqa: S311
                else random.randint(reorder_level, 300)  # noqa: S311
            )
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
                    fake.catch_phrase()[:80],
                    random.choice(["Electronics", "Office", "Supplies"]),  # noqa: S311
                    qty,
                    reorder_level,
                    _transaction_date(),
                ),
            )
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Append a new batch of raw source data.")
    parser.add_argument("--customers", type=int, default=30, help="New CRM customer rows (default: 30)")
    parser.add_argument("--products", type=int, default=5, help="New WMS product rows (default: 5)")
    parser.add_argument("--orders", type=int, default=100, help="New OMS transaction rows (default: 100)")
    args = parser.parse_args()

    fake = _fake_and_seed()
    conn = psycopg2.connect(settings.database_url.replace("+psycopg2", ""))
    cursor = conn.cursor()

    sku_base = _next_sku_base(cursor)

    # Pull all existing emails and item_codes so new orders can reference old customers/products too
    cursor.execute("SELECT email_address FROM raw.crm_customers")
    existing_emails = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT item_code FROM raw.wms_inventory")
    existing_item_codes = [row[0] for row in cursor.fetchall()]

    print(f"Adding batch — {args.customers} customers, {args.products} products, {args.orders} orders")
    print(f"  Existing pool: {len(existing_emails)} emails, {len(existing_item_codes)} SKUs")

    new_emails = add_customers(cursor, fake, args.customers)
    new_item_codes = add_products(cursor, fake, args.products, sku_base)

    all_emails = existing_emails + new_emails
    all_item_codes = existing_item_codes + new_item_codes
    add_orders(cursor, fake, all_emails, all_item_codes, args.orders)

    stock_count = 0
    if new_item_codes:
        stock_count = add_warehouse_stock(cursor, fake, new_item_codes)

    conn.commit()
    cursor.close()
    conn.close()

    print(
        f"\nBatch added (created_at = NOW()):\n"
        f"  raw.crm_customers     +{args.customers} rows  "
        f"(new emails: {new_emails[:3]}{'...' if len(new_emails) > 3 else ''})\n"
        f"  raw.wms_inventory     +{args.products} rows  (SKUs: {new_item_codes})\n"
        f"  raw.oms_transactions  +{args.orders} rows\n"
        f"  raw.warehouse_stock   +{stock_count} rows\n"
        f"\nWatermarks are unchanged — re-run the DAGs to pick up only these new rows."
    )


if __name__ == "__main__":
    main()
