"""Q2: Repeat-purchase rate and time between 1st and 2nd purchase."""

import plotly.express as px
import streamlit as st
from common import (
    ORANGE,
    filtered_orders_cte,
    kpi_row,
    render_global_filters,
    run_query,
)

st.set_page_config(page_title="Repeat Purchase", page_icon=":bar_chart:", layout="wide")
st.title("Repeat-Purchase Rate & Time to 2nd Order")
st.caption("SQL: `sql/02_repeat_purchase_rate_and_time_to_second_order.sql`")

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)

# order_seq comes from the precomputed customer_order_seq table (see
# database/build_olist_db.py) -- no ROW_NUMBER() recomputation here.
kpi_query = f"""
WITH {cte},
customer_orders AS (
    SELECT cos.customer_unique_id, cos.order_seq
    FROM customer_order_seq cos
    JOIN filtered_orders fo ON fo.order_id = cos.order_id
),
-- COUNT(*), not MAX(order_seq): total_orders must be "how many of this
-- customer's orders pass the current filter", not their global order count.
per_customer AS (SELECT customer_unique_id, COUNT(*) AS total_orders FROM customer_orders GROUP BY customer_unique_id)
SELECT
    COUNT(*) AS total_customers,
    SUM(CASE WHEN total_orders >= 2 THEN 1 ELSE 0 END) AS repeat_customers,
    ROUND(100.0 * SUM(CASE WHEN total_orders >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS repeat_rate
FROM per_customer
"""
kpis = run_query(kpi_query, params).iloc[0]

gaps_query = f"""
WITH {cte},
customer_orders AS (
    SELECT cos.customer_unique_id, cos.order_seq, o.order_purchase_timestamp,
           LAG(o.order_purchase_timestamp) OVER (
               PARTITION BY cos.customer_unique_id ORDER BY cos.order_seq
           ) AS prev_ts
    FROM orders o
    JOIN customer_order_seq cos ON cos.order_id = o.order_id
    JOIN filtered_orders fo ON fo.order_id = o.order_id
)
SELECT julianday(order_purchase_timestamp) - julianday(prev_ts) AS days_to_2nd_order
FROM customer_orders WHERE order_seq = 2
"""
gaps_df = run_query(gaps_query, params)

kpi_row([
    ("Total customers", f"{int(kpis['total_customers']):,}"),
    ("Repeat customers", f"{int(kpis['repeat_customers']):,}"),
    ("Repeat-purchase rate", f"{kpis['repeat_rate']:.2f}%"),
    ("Avg days to 2nd order", f"{gaps_df['days_to_2nd_order'].mean():.1f}" if not gaps_df.empty else "n/a"),
    ("Median days to 2nd order", f"{gaps_df['days_to_2nd_order'].median():.1f}" if not gaps_df.empty else "n/a"),
])

st.divider()
if gaps_df.empty:
    st.info("No repeat customers in the current filter selection.")
else:
    fig = px.histogram(gaps_df, x="days_to_2nd_order", nbins=40, color_discrete_sequence=[ORANGE])
    fig.update_layout(xaxis_title="Days between 1st and 2nd order", yaxis_title="Customers")
    st.plotly_chart(fig, use_container_width=True)
