"""Build olist.db from the raw Olist Kaggle CSVs.

Source: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
Expects the 9 olist_*.csv files unzipped into data/raw/ (see README "Reproduce").

geolocation.csv is intentionally not loaded: customers/sellers already carry
customer_state/seller_state directly, which is all the region filters need,
and geolocation is by far the largest file (~1M rows of zip-code lat/long)
for no analytical value here.
"""

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

TABLES = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

ORDER_DATE_COLS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]

REVIEW_DATE_COLS = ["review_creation_date", "review_answer_timestamp"]

# Kept deliberately lean: at ~100k rows per table, SQLite resolves every join
# in this project (even 5-way joins) in well under a second with no indexes
# at all (measured). customer_unique_id and order_purchase_timestamp are the
# two columns filtered/grouped by on nearly every dashboard query, so they're
# worth the ~7MB. A full FK index set (one per join column) was measured at
# +38MB — enough to push the committed .db over GitHub's 100MB file limit for
# no measurable query-time benefit at this data size.
INDEXES = [
    "CREATE INDEX idx_customers_unique_id ON customers(customer_unique_id)",
    "CREATE INDEX idx_orders_purchase_ts ON orders(order_purchase_timestamp)",
    "CREATE INDEX idx_cos_order_id ON customer_order_seq(order_id)",
]

# Every cohort/repeat-purchase page needs "which number order is this for this
# customer" (ROW_NUMBER() PARTITION BY customer_unique_id ORDER BY purchase
# timestamp). Precomputing it once here means every dashboard query joins to a
# small indexed table instead of re-scanning and re-ranking the full
# orders x customers join on every page load and every filter change. This
# global order_seq is independent of any dashboard filter (a customer's first
# order doesn't change because you filtered to one state), which is also the
# more defensible cohort semantics.
CUSTOMER_ORDER_SEQ_SQL = """
CREATE TABLE customer_order_seq AS
SELECT
    c.customer_unique_id,
    o.order_id,
    o.order_purchase_timestamp,
    ROW_NUMBER() OVER (
        PARTITION BY c.customer_unique_id ORDER BY o.order_purchase_timestamp
    ) AS order_seq
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
"""


def build(raw_dir: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    conn = sqlite3.connect(output_path)

    for table, filename in TABLES.items():
        df = pd.read_csv(raw_dir / filename)

        if table == "orders":
            for col in ORDER_DATE_COLS:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        if table == "order_reviews":
            for col in REVIEW_DATE_COLS:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        df.to_sql(table, conn, if_exists="replace", index=False)
        print(f"loaded {table}: {len(df):,} rows")

    cur = conn.cursor()
    cur.execute(CUSTOMER_ORDER_SEQ_SQL)
    print(f"built customer_order_seq: {cur.execute('SELECT COUNT(*) FROM customer_order_seq').fetchone()[0]:,} rows")

    for stmt in INDEXES:
        cur.execute(stmt)
    conn.commit()
    conn.execute("VACUUM")

    row_counts = {
        table: cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in {**TABLES, "customer_order_seq": None}
    }
    conn.close()

    print("\nfinal row counts:")
    for table, count in row_counts.items():
        print(f"  {table}: {count:,}")
    print(f"\nwrote {output_path} ({output_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "raw",
        help="Directory containing the unzipped Olist CSVs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "olist.db",
        help="Path to write the SQLite database to",
    )
    args = parser.parse_args()
    build(args.raw_dir, args.output)
