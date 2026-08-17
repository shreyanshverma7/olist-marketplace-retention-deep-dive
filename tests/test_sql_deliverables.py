"""Structural regression tests for every sql/*.sql deliverable.

CI already runs each file via the sqlite3 CLI, but only checks that it
*executes* -- output is piped to /dev/null. These tests upgrade that to
asserting each statement returns non-empty rows with the exact expected
column set, which catches an accidental column rename/drop/reorder that the
CLI-only check would silently let through.

Four files (04, 05, 06, 08) each contain two independent SELECT statements
meant to be run separately -- see each file's own header comment. Statements
are split on semicolons after stripping full-line `--` comments, which is
safe here since none of these hand-authored analytical queries embed a
semicolon inside a string literal.
"""

from pathlib import Path

import pytest

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

# (filename, [expected column list per statement, in file order])
EXPECTED_COLUMNS = {
    "01_monthly_cohort_retention.sql": [
        ["cohort_month", "cohort_size", "month_number", "active_customers", "retention_pct", "months_observable"],
    ],
    "02_repeat_purchase_rate_and_time_to_second_order.sql": [
        ["total_customers", "repeat_customers", "repeat_purchase_rate_pct", "avg_days_to_2nd_order", "median_days_to_2nd_order"],
    ],
    "03_category_first_vs_repeat_purchase.sql": [
        ["category", "purchase_type", "item_count", "pct_of_purchase_type"],
    ],
    "04_delivery_time_vs_review_score.sql": [
        ["delivery_bucket", "on_time_flag", "orders", "avg_review_score", "pct_bad_review"],
        ["n", "pearson_r"],
    ],
    "05_revenue_concentration_pareto_customers_sellers.sql": [
        ["rnk", "customer_unique_id", "revenue", "cumulative_pct_customers", "cumulative_pct_revenue"],
        ["rnk", "seller_id", "revenue", "cumulative_pct_sellers", "cumulative_pct_revenue"],
    ],
    "06_payment_installments_vs_order_value_and_repeat.sql": [
        ["installment_bucket", "primary_payment_type", "orders", "avg_order_value_brl"],
        ["primary_payment_type", "customers", "repeat_customers", "repeat_purchase_rate_pct"],
    ],
    "07_freight_cost_ratio_by_region.sql": [
        ["seller_state", "items", "avg_price_brl", "avg_freight_brl", "avg_freight_ratio", "avg_review_score", "pct_bad_review"],
    ],
    "08_order_status_funnel.sql": [
        ["stage", "orders", "pct_of_purchased", "pct_of_prior_stage"],
        ["order_status", "furthest_stage_reached", "orders"],
    ],
    "09_customer_segments_rfm.sql": [
        ["segment", "customers", "pct_of_customers", "avg_monetary", "total_monetary", "pct_of_revenue"],
    ],
}


def _split_statements(sql_text: str) -> list[str]:
    without_comments = "\n".join(
        line for line in sql_text.splitlines() if not line.strip().startswith("--")
    )
    return [s.strip() for s in without_comments.split(";") if s.strip()]


@pytest.fixture(scope="module")
def sql_files():
    files = sorted(SQL_DIR.glob("*.sql"))
    assert len(files) == 9, f"expected 9 SQL deliverables, found {len(files)}"
    return files


def test_every_expected_file_exists(sql_files):
    found_names = {f.name for f in sql_files}
    assert found_names == set(EXPECTED_COLUMNS)


@pytest.mark.parametrize("filename", sorted(EXPECTED_COLUMNS))
def test_statement_columns_and_non_empty(db_conn, filename):
    text = (SQL_DIR / filename).read_text()
    statements = _split_statements(text)
    expected = EXPECTED_COLUMNS[filename]

    assert len(statements) == len(expected), (
        f"{filename}: found {len(statements)} statement(s), expected {len(expected)}"
    )

    for i, (stmt, expected_cols) in enumerate(zip(statements, expected)):
        cur = db_conn.execute(stmt)
        actual_cols = [d[0] for d in cur.description]
        assert actual_cols == expected_cols, f"{filename} statement {i}: column mismatch"

        rows = cur.fetchall()
        assert len(rows) > 0, f"{filename} statement {i}: returned no rows"


@pytest.mark.parametrize("filename", ["01_monthly_cohort_retention.sql", "03_category_first_vs_repeat_purchase.sql", "07_freight_cost_ratio_by_region.sql", "09_customer_segments_rfm.sql"])
def test_percentage_columns_are_in_sane_range(db_conn, filename):
    """Spot-check files whose output includes a %-of-total-style column: every
    percentage value should sit in [0, 100], not overflow from a denominator
    bug (e.g. accidentally dividing by a subset instead of the full total)."""
    pct_column_by_file = {
        "01_monthly_cohort_retention.sql": "retention_pct",
        "03_category_first_vs_repeat_purchase.sql": "pct_of_purchase_type",
        "07_freight_cost_ratio_by_region.sql": "pct_bad_review",
        "09_customer_segments_rfm.sql": "pct_of_customers",
    }
    text = (SQL_DIR / filename).read_text()
    stmt = _split_statements(text)[0]
    column = pct_column_by_file[filename]

    df_rows = db_conn.execute(stmt).fetchall()
    col_index = [d[0] for d in db_conn.execute(stmt).description].index(column)
    values = [row[col_index] for row in df_rows if row[col_index] is not None]

    assert values, f"{filename}: no non-null values in {column}"
    assert all(0 <= v <= 100 for v in values), f"{filename}: {column} has a value outside [0, 100]"
