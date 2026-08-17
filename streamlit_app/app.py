"""Home / Executive Summary: KPI header, global filters, top findings, and the
quantified recommendation -- so a reviewer who only opens the live app (and
never GitHub) still gets the full story in one skim."""

import streamlit as st
from common import filtered_orders_cte, kpi_row, render_global_filters, run_query

st.set_page_config(page_title="Olist Retention Deep-Dive", page_icon="📊", layout="wide")

st.title("📊 Olist E-commerce Behaviour & Cohort Analysis")
st.caption(
    "~100k real orders from the Brazilian Olist marketplace (2016-2018). "
    "All figures in R$ (Brazilian Real)."
)

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)

# Three single-pass queries instead of one query with 5 correlated subqueries
# against a shared CTE. SQLite doesn't materialize non-recursive CTEs by
# default, so referencing one CTE from 5 separate scalar subqueries re-runs
# the underlying join 5 times over -- that was costing ~3s on every new
# filter combination. Each query below joins its own tables exactly once.
with st.spinner("Querying orders..."):
    counts_sql = f"""
    WITH {cte},
    per_customer AS (
        SELECT c.customer_unique_id, COUNT(*) AS n_orders
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        JOIN filtered_orders fo ON fo.order_id = o.order_id
        GROUP BY c.customer_unique_id
    )
    SELECT
        COUNT(*) AS n_customers,
        SUM(n_orders) AS n_orders,
        ROUND(100.0 * SUM(CASE WHEN n_orders >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS repeat_rate
    FROM per_customer
    """
    counts = run_query(counts_sql, params).iloc[0]

    revenue_sql = f"""
    WITH {cte}
    SELECT ROUND(SUM(oi.price + oi.freight_value), 2) AS revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    JOIN filtered_orders fo ON fo.order_id = o.order_id
    WHERE o.order_status = 'delivered'
    """
    revenue = run_query(revenue_sql, params).iloc[0]["revenue"]

    review_sql = f"""
    WITH {cte}
    SELECT ROUND(AVG(r.review_score), 2) AS avg_review
    FROM orders o
    JOIN order_reviews r ON r.order_id = o.order_id
    JOIN filtered_orders fo ON fo.order_id = o.order_id
    """
    avg_review = run_query(review_sql, params).iloc[0]["avg_review"]

kpi_row([
    ("Orders", f"{int(counts['n_orders']):,}", "Count of orders matching the current filters."),
    ("Unique customers", f"{int(counts['n_customers']):,}", "Distinct customer_unique_id -- the real person, not the per-order customer_id."),
    ("Repeat-purchase rate", f"{counts['repeat_rate']:.2f}%", "% of customers with 2+ orders within the current filter selection."),
    ("Delivered GMV", f"R$ {revenue:,.0f}" if revenue is not None else "R$ 0", "Sum of item price + freight, delivered orders only."),
    ("Avg review score", f"{avg_review:.2f} / 5" if avg_review is not None else "n/a", "Mean review_score (1-5) across reviewed orders in the current filter."),
])

st.divider()

st.subheader("Top 3 findings")
st.markdown(
    """
1. **Retention is the headline problem, not a footnote.** Fewer than 3.2% of customers ever place a
   second order, and month-1 cohort retention sits well under 1% for every cohort with a full observation
   window. This is a real-data result (not a synthetic-generator artifact) -- see **Cohort Retention**.
2. **Late delivery is the strongest, cleanest signal in the whole dataset.** Orders that arrive after
   Olist's own estimated date get a bad review (score ≤ 2) 54.0% of the time, vs. 9.2% for on-time
   orders -- a difference that survives Holm-Bonferroni correction by a wide margin. See **Delivery vs. Reviews**
   and **Statistical Tests**.
3. **Revenue concentration looks very different on the seller side than the customer side.** The top 5%
   of customers drive 26.8% of GMV -- meaningful but not fragile. The top 5% of sellers drive 52.3% of GMV --
   half the marketplace's revenue depends on a small slice of sellers. See **Revenue Concentration**.
    """
)

st.subheader("Recommendation, prioritized and quantified")
st.markdown(
    """
1. **Fix delivery-estimate accuracy and late-shipment logistics first.** It's the single largest,
   most statistically robust lever on satisfaction found in this analysis -- a 44.8-point swing in
   bad-review rate (54.0% vs. 9.2%) between late and on-time orders, on a sample of 96k+ orders. Target
   the highest-freight-ratio seller states first (CE, ES, GO, DF all sit above a 0.36 freight/price
   ratio) -- see **Logistics Freight**.
2. **Build a second-purchase program, not just an acquisition funnel.** With repeat-purchase rate at
   3.12% and a median 27.9 days between the 1st and 2nd order, there's a real but narrow window to
   re-engage a first-time buyer before they're gone for good. `bed_bath_table` customers are the
   strongest repeat-purchase segment -- a natural place to pilot a win-back campaign. See
   **Category Drilldown** and **Customer Segments (RFM)**.
3. **Treat seller concentration as a platform risk, not just a revenue fact.** At 52.3% of GMV from
   the top 5% of sellers, a seller-retention/diversification program is a bigger structural priority
   than deepening the customer base, where revenue is comparatively well spread. See
   **Revenue Concentration**.
    """
)

st.info(
    "Use the sidebar to filter by date range, customer state, product category, and payment type -- "
    "every page (including these KPIs) re-queries the live database on any filter change.",
    icon="ℹ️",
)

st.divider()
st.caption(
    "Data: [Olist Brazilian E-Commerce (Kaggle)](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). "
    "See NOTICE.md for the dataset's license terms."
)
