"""Shared DB connection, query helper, and global sidebar filters.

Every page calls render_global_filters() at the top and gets back a Filters
object plus a ready-to-use "filtered_orders" CTE fragment -- every page's SQL
prepends that CTE and joins to it, so the date/state/category/payment-type
filters apply identically everywhere without duplicating filter logic per page.
Widgets use fixed keys, which is how Streamlit persists filter selections
across page navigation within a session (shared sidebar state).
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "olist.db"

ORANGE = "#D97757"

# Shared categorical palette so every multi-series chart in the app (not just
# the two-way first/repeat or on-time/late charts) stays on the same orange +
# neutral-gray system instead of falling back to Plotly's default qualitative
# palette (which reads as an unrelated, clashing color scheme against the
# dark theme).
PAYMENT_TYPE_COLORS = {
    "credit_card": ORANGE,
    "boleto": "#C9A227",
    "debit_card": "#8a8a8a",
    "voucher": "#5a5a5a",
}


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)


@st.cache_data
def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Cached by (sql, params) -- a filter change is a cache miss, so every
    chart recomputes live against the current filter selection rather than
    reading a static export."""
    return pd.read_sql_query(sql, get_connection(), params=params)


@st.cache_data
def _filter_options():
    conn = get_connection()
    states = pd.read_sql_query(
        "SELECT DISTINCT customer_state FROM customers ORDER BY 1", conn
    )["customer_state"].tolist()
    categories = pd.read_sql_query(
        """
        SELECT DISTINCT COALESCE(t.product_category_name_english, p.product_category_name) AS category
        FROM products p
        LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
        WHERE category IS NOT NULL
        ORDER BY 1
        """,
        conn,
    )["category"].tolist()
    payment_types = pd.read_sql_query(
        "SELECT DISTINCT payment_type FROM order_payments WHERE payment_type != 'not_defined' ORDER BY 1",
        conn,
    )["payment_type"].tolist()
    bounds = pd.read_sql_query(
        "SELECT MIN(order_purchase_timestamp) AS lo, MAX(order_purchase_timestamp) AS hi FROM orders", conn
    ).iloc[0]
    return states, categories, payment_types, bounds["lo"][:10], bounds["hi"][:10]


@dataclass
class Filters:
    start_date: str
    end_date: str
    states: list = field(default_factory=list)
    categories: list = field(default_factory=list)
    payment_types: list = field(default_factory=list)


def render_global_filters() -> Filters:
    states, categories, payment_types, lo, hi = _filter_options()

    # Default to the dense, analytically meaningful window (matches the cohort
    # SQL's own restriction) rather than the full raw range, which includes a
    # near-empty 2016 pilot period and a near-empty 2018-09/10 tail. Full range
    # is still reachable via min_value/max_value.
    default_start = max(pd.to_datetime(lo), pd.to_datetime("2017-01-01"))
    default_end = min(pd.to_datetime(hi), pd.to_datetime("2018-08-31"))

    st.sidebar.header("Filters")
    date_range = st.sidebar.date_input(
        "Order date range", value=(default_start, default_end),
        min_value=pd.to_datetime(lo), max_value=pd.to_datetime(hi), key="filter_date_range",
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = str(date_range[0]), str(date_range[1])
    else:
        start_date, end_date = lo, hi

    sel_states = st.sidebar.multiselect("Customer state", states, key="filter_states")
    sel_categories = st.sidebar.multiselect("Product category", categories, key="filter_categories")
    sel_payment_types = st.sidebar.multiselect("Payment type", payment_types, key="filter_payment_types")

    st.sidebar.caption(
        "Leave a filter empty to include all values. Filters apply live -- "
        "every chart re-queries olist.db on change."
    )

    return Filters(start_date, end_date, sel_states, sel_categories, sel_payment_types)


def filtered_orders_cte(filters: Filters) -> tuple[str, tuple]:
    """Returns (cte_sql, params). Prepend the CTE with `WITH ... , {cte_sql}`
    (it's written as a bare CTE body, no leading WITH) and join pages' queries
    to `filtered_orders fo ON fo.order_id = o.order_id`."""
    conditions = ["o.order_purchase_timestamp BETWEEN ? AND ?"]
    params: list = [filters.start_date, filters.end_date + " 23:59:59"]

    joins = ["orders o", "JOIN customers c ON o.customer_id = c.customer_id"]

    if filters.states:
        conditions.append(f"c.customer_state IN ({','.join('?' * len(filters.states))})")
        params.extend(filters.states)

    if filters.categories:
        joins.append("JOIN order_items oi_f ON oi_f.order_id = o.order_id")
        joins.append("JOIN products p_f ON p_f.product_id = oi_f.product_id")
        joins.append("LEFT JOIN category_translation t_f ON t_f.product_category_name = p_f.product_category_name")
        conditions.append(
            f"COALESCE(t_f.product_category_name_english, p_f.product_category_name) IN "
            f"({','.join('?' * len(filters.categories))})"
        )
        params.extend(filters.categories)

    if filters.payment_types:
        joins.append("JOIN order_payments pay_f ON pay_f.order_id = o.order_id")
        conditions.append(f"pay_f.payment_type IN ({','.join('?' * len(filters.payment_types))})")
        params.extend(filters.payment_types)

    cte = f"""
    filtered_orders AS (
        SELECT DISTINCT o.order_id
        FROM {' '.join(joins)}
        WHERE {' AND '.join(conditions)}
    )
    """
    return cte, tuple(params)


def kpi_row(items: list[tuple[str, str]]) -> None:
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.metric(label, value)
