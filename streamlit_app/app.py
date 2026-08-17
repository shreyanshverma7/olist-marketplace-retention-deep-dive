"""Home page: KPI header, global filters, and the top-3 findings."""

import streamlit as st
from common import filtered_orders_cte, kpi_row, render_global_filters, run_query

st.set_page_config(page_title="Olist Retention Deep-Dive", page_icon=":bar_chart:", layout="wide")

st.title("Olist E-commerce Behaviour & Cohort Analysis")
st.caption(
    "~100k real orders from the Brazilian Olist marketplace (2016-2018). "
    "All figures in R$ (Brazilian Real)."
)

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)

kpi_sql = f"""
WITH {cte},
scoped_orders AS (
    SELECT o.*, c.customer_unique_id
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
    JOIN filtered_orders fo ON fo.order_id = o.order_id
),
per_customer AS (
    SELECT customer_unique_id, COUNT(*) AS n_orders
    FROM scoped_orders
    GROUP BY customer_unique_id
)
SELECT
    (SELECT COUNT(*) FROM scoped_orders) AS n_orders,
    (SELECT COUNT(DISTINCT customer_unique_id) FROM scoped_orders) AS n_customers,
    (SELECT ROUND(100.0 * SUM(CASE WHEN n_orders >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) FROM per_customer) AS repeat_rate,
    (SELECT ROUND(SUM(oi.price + oi.freight_value), 2)
       FROM order_items oi JOIN scoped_orders so ON so.order_id = oi.order_id
       WHERE so.order_status = 'delivered') AS revenue,
    (SELECT ROUND(AVG(r.review_score), 2)
       FROM order_reviews r JOIN scoped_orders so ON so.order_id = r.order_id) AS avg_review
"""
kpis = run_query(kpi_sql, params).iloc[0]

kpi_row([
    ("Orders", f"{int(kpis['n_orders']):,}"),
    ("Unique customers", f"{int(kpis['n_customers']):,}"),
    ("Repeat-purchase rate", f"{kpis['repeat_rate']:.2f}%"),
    ("Delivered GMV", f"R$ {kpis['revenue']:,.0f}"),
    ("Avg review score", f"{kpis['avg_review']:.2f} / 5"),
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
   of customers drive 26.8% of GMV -- meaningful but not fragile. The top 5% of sellers drive 53.0% of GMV --
   half the marketplace's revenue depends on a small slice of sellers. See **Revenue Concentration**.
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
