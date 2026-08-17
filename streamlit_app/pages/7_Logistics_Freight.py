"""Q7: Freight cost concentration by seller state, vs. review score."""

import plotly.express as px
import streamlit as st
from common import ORANGE, filtered_orders_cte, render_global_filters, run_query

st.set_page_config(page_title="Logistics & Freight", page_icon=":bar_chart:", layout="wide")
st.title("Freight Cost Concentration by Region")
st.caption("SQL: `sql/07_freight_cost_ratio_by_region.sql`")

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)

query = f"""
WITH {cte},
item_freight AS (
    SELECT s.seller_state, oi.price, oi.freight_value,
           oi.freight_value / oi.price AS freight_ratio, r.review_score
    FROM orders o
    JOIN filtered_orders fo ON fo.order_id = o.order_id
    JOIN order_items oi ON oi.order_id = o.order_id
    JOIN sellers s ON s.seller_id = oi.seller_id
    JOIN order_reviews r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered' AND oi.price > 0
)
SELECT seller_state, COUNT(*) AS items,
       ROUND(AVG(price), 2) AS avg_price, ROUND(AVG(freight_value), 2) AS avg_freight,
       ROUND(AVG(freight_ratio), 4) AS avg_freight_ratio,
       ROUND(AVG(review_score), 2) AS avg_review_score,
       ROUND(100.0 * SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_bad_review
FROM item_freight GROUP BY seller_state HAVING COUNT(*) >= 30
ORDER BY avg_freight_ratio DESC
"""
df = run_query(query, params)

if df.empty:
    st.info("No items in the current filter selection (states with fewer than 30 items are dropped).")
    st.stop()

fig = px.bar(
    df, x="seller_state", y="avg_freight_ratio", color="pct_bad_review",
    color_continuous_scale=[[0, "#3a3a3a"], [1, ORANGE]],
    labels={"avg_freight_ratio": "Avg freight / price ratio", "seller_state": "Seller state",
            "pct_bad_review": "% bad reviews"},
)
st.plotly_chart(fig, use_container_width=True)
st.caption(
    "Freight ratio = freight_value / price, so it's comparable across cheap and expensive items. "
    "Bar color shows each state's bad-review rate (score <= 2)."
)
st.dataframe(df, use_container_width=True, hide_index=True)
