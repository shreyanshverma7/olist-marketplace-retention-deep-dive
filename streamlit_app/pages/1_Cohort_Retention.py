"""Q1: Monthly cohort retention triangle."""

import plotly.express as px
import streamlit as st
from common import ORANGE, filtered_orders_cte, render_global_filters, run_query

st.set_page_config(page_title="Cohort Retention", page_icon=":bar_chart:", layout="wide")
st.title("Monthly Cohort Retention")
st.caption("SQL: `sql/01_monthly_cohort_retention.sql`")

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)

# order_seq comes from the precomputed customer_order_seq table (see
# database/build_olist_db.py) instead of recomputing ROW_NUMBER() on every
# query. It's a global rank over each customer's full order history, so a
# customer's cohort_month doesn't shift depending on the sidebar filters --
# filtering only changes which of their orders count as "activity" below.
query = f"""
WITH {cte},
scoped AS (
    SELECT cos.customer_unique_id, o.order_purchase_timestamp, cos.order_seq
    FROM orders o
    JOIN customer_order_seq cos ON cos.order_id = o.order_id
    JOIN filtered_orders fo ON fo.order_id = o.order_id
),
cohorts AS (
    SELECT customer_unique_id, strftime('%Y-%m', order_purchase_timestamp) AS cohort_month
    FROM scoped
    WHERE order_seq = 1
      AND order_purchase_timestamp >= '2017-01-01' AND order_purchase_timestamp < '2018-09-01'
),
activity AS (
    SELECT
        coh.cohort_month,
        s.customer_unique_id,
        (CAST(strftime('%Y', s.order_purchase_timestamp) AS INT) - CAST(substr(coh.cohort_month,1,4) AS INT)) * 12
          + (CAST(strftime('%m', s.order_purchase_timestamp) AS INT) - CAST(substr(coh.cohort_month,6,2) AS INT)) AS month_number
    FROM scoped s JOIN cohorts coh ON coh.customer_unique_id = s.customer_unique_id
),
cohort_sizes AS (SELECT cohort_month, COUNT(*) AS cohort_size FROM cohorts GROUP BY cohort_month),
triangle AS (
    SELECT cohort_month, month_number, COUNT(DISTINCT customer_unique_id) AS active
    FROM activity GROUP BY cohort_month, month_number
)
SELECT t.cohort_month, cs.cohort_size, t.month_number,
       ROUND(100.0 * t.active / cs.cohort_size, 2) AS retention_pct
FROM triangle t JOIN cohort_sizes cs ON cs.cohort_month = t.cohort_month
ORDER BY t.cohort_month, t.month_number
"""
df = run_query(query, params)

if df.empty:
    st.warning("No cohorts in the current filter selection (2017-01 to 2018-08 only -- widen the date range).")
    st.stop()

st.warning(
    "**Observation-window caveat:** later cohorts have had less time to return. Only compare cohorts "
    "at the same month_number, and treat cohorts near the right edge of the triangle as incomplete.",
    icon="⚠️",
)

# month_number=0 is always 100% by definition (the cohort's first order) --
# leaving it in the color/height scale flattens every other month, which is
# the interesting part of the story, into an indistinguishable near-zero.
# Excluded from the charts below only; still in the raw table.
chart_df = df[df["month_number"] > 0]

st.caption("month 0 (100% by definition) is omitted from the charts below for readability.")

pivot = chart_df.pivot(index="cohort_month", columns="month_number", values="retention_pct")
fig = px.imshow(
    pivot, color_continuous_scale=[[0, "#1a1a1a"], [1, ORANGE]],
    labels={"x": "Months since first order", "y": "Cohort", "color": "Retention %"},
    aspect="auto",
)
fig.update_layout(height=500)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Drill down into one cohort")
cohort_options = sorted(df["cohort_month"].unique())
cohort_choice = st.selectbox("Cohort", cohort_options, index=0)  # earliest cohort = fullest observation window
cohort_df = df[df["cohort_month"] == cohort_choice].sort_values("month_number")
cohort_chart_df = cohort_df[cohort_df["month_number"] > 0]
if cohort_chart_df.empty:
    st.info("This cohort has no activity beyond month 0 in the current filter selection.")
else:
    fig2 = px.bar(cohort_chart_df, x="month_number", y="retention_pct", color_discrete_sequence=[ORANGE])
    fig2.update_layout(xaxis_title="Months since first order", yaxis_title="Retention %")
    st.plotly_chart(fig2, use_container_width=True)
st.dataframe(cohort_df, use_container_width=True, hide_index=True)
