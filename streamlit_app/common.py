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


def inject_custom_css() -> None:
    """Restyles st.metric into a bordered card with an orange accent, and a
    couple of other small touches -- still plain st.metric/st.info underneath,
    just CSS, so it carries zero functional risk."""
    st.markdown(
        f"""
        <style>
        [data-testid="stMetric"] {{
            background-color: #1A1A1D;
            border: 1px solid #2a2a2e;
            border-left: 3px solid {ORANGE};
            border-radius: 8px;
            padding: 14px 16px 10px 16px;
        }}
        [data-testid="stMetricLabel"] {{ opacity: 0.75; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _apply_date_preset(start, end) -> None:
    st.session_state["filter_date_range"] = (start, end)


def render_global_filters() -> Filters:
    inject_custom_css()
    states, categories, payment_types, lo, hi = _filter_options()
    lo_ts, hi_ts = pd.to_datetime(lo), pd.to_datetime(hi)

    # Default to the dense, analytically meaningful window (matches the cohort
    # SQL's own restriction) rather than the full raw range, which includes a
    # near-empty 2016 pilot period and a near-empty 2018-09/10 tail. Full range
    # is still reachable via min_value/max_value.
    default_start = max(lo_ts, pd.to_datetime("2017-01-01"))
    default_end = min(hi_ts, pd.to_datetime("2018-08-31"))

    st.sidebar.header("Filters")

    st.sidebar.caption("Quick range (relative to the dataset's last order date)")
    preset_cols = st.sidebar.columns(3)
    preset_cols[0].button(
        "3mo", use_container_width=True,
        on_click=_apply_date_preset, args=(hi_ts - pd.Timedelta(days=90), hi_ts),
    )
    preset_cols[1].button(
        "6mo", use_container_width=True,
        on_click=_apply_date_preset, args=(hi_ts - pd.Timedelta(days=180), hi_ts),
    )
    preset_cols[2].button(
        "Full", use_container_width=True,
        on_click=_apply_date_preset, args=(lo_ts, hi_ts),
    )

    date_range = st.sidebar.date_input(
        "Order date range", value=(default_start, default_end),
        min_value=lo_ts, max_value=hi_ts, key="filter_date_range",
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
    to `filtered_orders fo ON fo.order_id = o.order_id`.

    Both the customers join and DISTINCT are conditional, not unconditional --
    each was measured to cost ~0.3-0.5s on its own at this row count (customers
    joins on a 32-char TEXT key; DISTINCT sorts ~90k TEXT order_ids), and every
    page pays this cost on every query since every page calls this function.
    Only pay for what a given filter selection actually needs: the customers
    join is only required for the state filter, and DISTINCT is only required
    when a category/payment-type filter joins in a one-to-many table
    (order_items/order_payments) that can produce duplicate order_ids.
    """
    conditions = ["o.order_purchase_timestamp BETWEEN ? AND ?"]
    params: list = [filters.start_date, filters.end_date + " 23:59:59"]

    joins = ["orders o"]
    needs_distinct = False

    if filters.states:
        joins.append("JOIN customers c ON o.customer_id = c.customer_id")
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
        needs_distinct = True  # an order can have multiple items, so this join can fan out

    if filters.payment_types:
        joins.append("JOIN order_payments pay_f ON pay_f.order_id = o.order_id")
        conditions.append(f"pay_f.payment_type IN ({','.join('?' * len(filters.payment_types))})")
        params.extend(filters.payment_types)
        needs_distinct = True  # an order can have multiple payment legs, same fan-out risk

    select_clause = "SELECT DISTINCT o.order_id" if needs_distinct else "SELECT o.order_id"
    # MATERIALIZED (SQLite >=3.35, 2021) forces this CTE to compute once and be
    # reused everywhere it's referenced. Without it, some pages reference
    # filtered_orders from two or more places inside one query (e.g. Payments
    # joins it once for payment ranking and again for customer order history)
    # -- SQLite's planner doesn't always choose to materialize a CTE on its
    # own, and inlining it repeatedly inside an already-multi-CTE query was
    # measured to blow up from ~1s to an unbounded hang (confirmed via
    # EXPLAIN QUERY PLAN: a full order-date-range scan was being re-run as the
    # driving loop of a nested join, once per outer reference). Explicit
    # MATERIALIZED removes the dependency on that planner heuristic entirely.
    cte = f"""
    filtered_orders AS MATERIALIZED (
        {select_clause}
        FROM {' '.join(joins)}
        WHERE {' AND '.join(conditions)}
    )
    """
    return cte, tuple(params)


def kpi_row(items: list[tuple[str, str]] | list[tuple[str, str, str]]) -> None:
    """Each item is (label, value) or (label, value, help_text) -- help_text
    becomes the native st.metric tooltip explaining how the number is computed."""
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        label, value = item[0], item[1]
        help_text = item[2] if len(item) > 2 else None
        col.metric(label, value, help=help_text)


def download_csv_button(df: pd.DataFrame, filename: str, label: str = "Download this data (CSV)") -> None:
    st.download_button(
        label, data=df.to_csv(index=False).encode("utf-8"),
        file_name=filename, mime="text/csv",
    )
