"""Q4: Does late delivery predict bad reviews?"""

import pandas as pd
import plotly.express as px
import streamlit as st
from common import (
    ORANGE,
    filtered_orders_cte,
    kpi_row,
    render_global_filters,
    run_query,
)
from scipy import stats

st.set_page_config(page_title="Delivery vs Reviews", page_icon=":bar_chart:", layout="wide")
st.title("Delivery Time vs. Review Score")
st.caption("SQL: `sql/04_delivery_time_vs_review_score.sql`")

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)

query = f"""
WITH {cte},
scored AS (
    SELECT
        julianday(o.order_delivered_customer_date) - julianday(o.order_purchase_timestamp) AS delivery_days,
        r.review_score,
        CASE WHEN o.order_delivered_customer_date <= o.order_estimated_delivery_date THEN 'on_time' ELSE 'late' END AS on_time_flag
    FROM orders o
    JOIN order_reviews r ON r.order_id = o.order_id
    JOIN filtered_orders fo ON fo.order_id = o.order_id
    WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
)
SELECT * FROM scored
"""
df = run_query(query, params)

if df.empty:
    st.info("No delivered+reviewed orders in the current filter selection.")
    st.stop()

r, p = stats.pearsonr(df["delivery_days"], df["review_score"])
bad_late = 100 * (df.loc[df.on_time_flag == "late", "review_score"] <= 2).mean()
bad_ontime = 100 * (df.loc[df.on_time_flag == "on_time", "review_score"] <= 2).mean()

kpi_row([
    ("Pearson r (days vs. score)", f"{r:.3f}"),
    ("p-value", f"{p:.2g}" if p > 0 else "<1e-300"),
    ("Bad-review rate, late", f"{bad_late:.1f}%"),
    ("Bad-review rate, on-time", f"{bad_ontime:.1f}%"),
])

df["delivery_bucket"] = pd.cut(
    df["delivery_days"], bins=[-1, 7, 14, 21, 30, 999],
    labels=["<7 days", "7-13 days", "14-20 days", "21-29 days", "30+ days"],
)
bucketed = (
    df.groupby(["delivery_bucket", "on_time_flag"], observed=True)
    .agg(orders=("review_score", "size"), avg_score=("review_score", "mean"),
         pct_bad=("review_score", lambda s: 100 * (s <= 2).mean()))
    .reset_index()
)

st.divider()
fig = px.bar(
    bucketed, x="delivery_bucket", y="pct_bad", color="on_time_flag", barmode="group",
    color_discrete_map={"on_time": "#3a3a3a", "late": ORANGE},
    labels={"pct_bad": "% bad reviews (score <= 2)", "delivery_bucket": "Delivery time"},
)
st.plotly_chart(fig, use_container_width=True)
st.dataframe(bucketed, use_container_width=True, hide_index=True)
