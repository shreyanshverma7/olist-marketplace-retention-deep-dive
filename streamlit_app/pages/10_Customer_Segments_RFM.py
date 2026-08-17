"""Q9: Customer segmentation adapted from RFM (Recency/Frequency/Monetary)."""

import plotly.express as px
import streamlit as st
from common import (
    ORANGE,
    download_csv_button,
    filtered_orders_cte,
    kpi_row,
    render_global_filters,
    run_query,
)

st.set_page_config(page_title="Customer Segments (RFM)", page_icon="👥", layout="wide")
st.title("👥 Customer Segments (RFM, Adapted)")
st.caption("SQL: `sql/09_customer_segments_rfm.sql`")

st.warning(
    "**Why this isn't textbook RFM:** standard 5-way frequency-quintile scoring doesn't fit this dataset "
    "honestly -- 96.9% of customers have exactly 1 order (see Repeat Purchase), so a frequency quintile "
    "would just be noise. Instead: a real repeat-vs-one-time split, then a monetary tercile x recency-half "
    "split *within* one-time customers only, so it isn't diluted by repeat customers' typically higher spend.",
    icon="⚠️",
)

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)

query = f"""
WITH {cte},
order_revenue AS (
    SELECT order_id, SUM(price + freight_value) AS revenue FROM order_items GROUP BY order_id
),
customer_agg AS (
    SELECT
        cos.customer_unique_id,
        COUNT(*) AS frequency,
        MAX(o.order_purchase_timestamp) AS last_order_ts,
        SUM(CASE WHEN o.order_status = 'delivered' THEN COALESCE(orv.revenue, 0) ELSE 0 END) AS monetary
    FROM customer_order_seq cos
    JOIN orders o ON o.order_id = cos.order_id
    JOIN filtered_orders fo ON fo.order_id = cos.order_id
    LEFT JOIN order_revenue orv ON orv.order_id = cos.order_id
    GROUP BY cos.customer_unique_id
),
one_time_scored AS (
    SELECT customer_unique_id, monetary, last_order_ts,
           NTILE(3) OVER (ORDER BY monetary) AS monetary_tercile,
           NTILE(2) OVER (ORDER BY last_order_ts) AS recency_half
    FROM customer_agg WHERE frequency = 1
),
segmented AS (
    SELECT customer_unique_id, monetary, 'Repeat customers' AS segment
    FROM customer_agg WHERE frequency >= 2
    UNION ALL
    SELECT customer_unique_id, monetary,
        (CASE monetary_tercile WHEN 1 THEN 'One-time: Low value' WHEN 2 THEN 'One-time: Mid value' ELSE 'One-time: High value' END)
        || ' / ' || (CASE recency_half WHEN 1 THEN 'Lapsed' ELSE 'Recent' END) AS segment
    FROM one_time_scored
)
SELECT
    segment,
    COUNT(*) AS customers,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM customer_agg), 2) AS pct_of_customers,
    ROUND(AVG(monetary), 2) AS avg_monetary,
    ROUND(SUM(monetary), 2) AS total_monetary,
    ROUND(100.0 * SUM(monetary) / (SELECT SUM(monetary) FROM customer_agg), 2) AS pct_of_revenue
FROM segmented
GROUP BY segment
ORDER BY total_monetary DESC
"""

with st.spinner("Segmenting customers..."):
    df = run_query(query, params)

if df.empty:
    st.info("No customers in the current filter selection.")
    st.stop()

repeat_row = df[df["segment"] == "Repeat customers"]
high_value_pct = df[df["segment"].str.contains("High value")]["pct_of_revenue"].sum()

kpi_row([
    ("Segments", f"{len(df)}"),
    ("Repeat customers", f"{repeat_row['pct_of_customers'].iloc[0]:.2f}% of customers" if not repeat_row.empty else "n/a",
     "Customers with 2+ orders in the current filter selection."),
    ("Repeat customers' revenue share", f"{repeat_row['pct_of_revenue'].iloc[0]:.2f}%" if not repeat_row.empty else "n/a"),
    ("One-time High-value revenue share", f"{high_value_pct:.1f}%",
     "Combined revenue share of 'One-time: High value / Recent' + 'One-time: High value / Lapsed'."),
])

st.divider()
col1, col2 = st.columns(2)
with col1:
    st.subheader("Customers by segment")
    fig1 = px.bar(
        df.sort_values("customers"), x="customers", y="segment", orientation="h",
        color_discrete_sequence=[ORANGE],
    )
    fig1.update_layout(yaxis_title="", xaxis_title="Customers")
    st.plotly_chart(fig1, use_container_width=True)
with col2:
    st.subheader("Revenue share by segment")
    fig2 = px.bar(
        df.sort_values("pct_of_revenue"), x="pct_of_revenue", y="segment", orientation="h",
        color_discrete_sequence=["#3a3a3a"],
    )
    fig2.update_layout(yaxis_title="", xaxis_title="% of total revenue")
    st.plotly_chart(fig2, use_container_width=True)

st.dataframe(df, use_container_width=True, hide_index=True)
download_csv_button(df, "customer_segments_rfm.csv")

st.info(
    "**So what:** one-time high-value customers (both recent and lapsed) drive roughly two-thirds of "
    "total revenue, while repeat customers -- despite spending ~2x more per person on average -- "
    "contribute under 6% of revenue simply because there are so few of them (3.12% of the base). The "
    "revenue backbone of this marketplace is big one-time spenders, not loyal repeat buyers, precisely "
    "because repeat behavior barely exists here. A win-back campaign aimed at lapsed high-value "
    "one-time customers is a concrete, sizeable target -- not a marginal one.",
    icon="💡",
)
