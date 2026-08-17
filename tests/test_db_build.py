"""Tests database/build_olist_db.py's ETL logic in full isolation from the
real ~89MB committed database, using a tiny hand-built synthetic CSV set
under tests/fixtures/raw_csv/ (data/raw/*.csv, the real Kaggle download, may
not be present in every checkout -- the README notes olist.db is already
committed and the real CSVs are only needed "to verify reproducibility").

The fixture set: 3 customers (customer_unique_id "unique_1" appears twice,
across cust_id_1 and cust_id_2, to exercise the repeat-customer path),
3 orders (order_1 2017-01-01, order_2 2017-02-01, order_3 2017-01-15),
3 order_items, 3 order_payments, 3 order_reviews, 2 products, 2 sellers,
2 category translations.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_RAW_DIR = Path(__file__).resolve().parent / "fixtures" / "raw_csv"

sys.path.insert(0, str(ROOT / "database"))
from build_olist_db import TABLES, build


@pytest.fixture(scope="module")
def built_db_conn(tmp_path_factory):
    output_path = tmp_path_factory.mktemp("db_build_test") / "test_olist.db"
    build(FIXTURE_RAW_DIR, output_path)
    conn = sqlite3.connect(output_path)
    yield conn
    conn.close()


def test_all_raw_tables_loaded_with_correct_row_counts(built_db_conn):
    expected_counts = {
        "customers": 3, "orders": 3, "order_items": 3, "order_payments": 3,
        "order_reviews": 3, "products": 2, "sellers": 2, "category_translation": 2,
    }
    for table in TABLES:
        n = built_db_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert n == expected_counts[table], f"{table}: expected {expected_counts[table]}, got {n}"


def test_customer_order_seq_derived_correctly(built_db_conn):
    rows = built_db_conn.execute(
        "SELECT customer_unique_id, order_id, order_seq FROM customer_order_seq ORDER BY customer_unique_id, order_seq"
    ).fetchall()
    assert len(rows) == 3

    # unique_1 has two orders (order_1 on 2017-01-01, order_2 on 2017-02-01)
    # -- ROW_NUMBER() PARTITION BY customer_unique_id ORDER BY purchase
    # timestamp must rank the earlier purchase first, regardless of
    # customer_id or row order in the source CSV.
    unique_1_rows = [r for r in rows if r[0] == "unique_1"]
    assert len(unique_1_rows) == 2
    assert {order_id: seq for _, order_id, seq in unique_1_rows} == {"order_1": 1, "order_2": 2}

    unique_2_rows = [r for r in rows if r[0] == "unique_2"]
    assert len(unique_2_rows) == 1
    assert unique_2_rows[0][1:] == ("order_3", 1)


def test_date_columns_parsed_and_orderable(built_db_conn):
    # pd.to_datetime + to_sql writes ISO-format strings, which sort correctly
    # as plain text -- confirms ORDER_DATE_COLS parsing didn't silently no-op.
    rows = built_db_conn.execute(
        "SELECT order_id FROM orders ORDER BY order_purchase_timestamp"
    ).fetchall()
    assert [r[0] for r in rows] == ["order_1", "order_3", "order_2"]


def test_expected_indexes_created(built_db_conn):
    index_names = {
        r[0] for r in built_db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert index_names == {"idx_customers_unique_id", "idx_orders_purchase_ts", "idx_cos_order_id"}


def test_geolocation_not_loaded(built_db_conn):
    tables = {
        r[0] for r in built_db_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "geolocation" not in tables
