"""Q8: Order-status funnel -- where do orders leak, and where do
cancellations/unavailability concentrate?"""

import plotly.graph_objects as go
import streamlit as st
from common import (
    ORANGE,
    download_csv_button,
    filtered_orders_cte,
    kpi_row,
    render_global_filters,
    run_query,
)

st.set_page_config(page_title="Order Status Funnel", page_icon="🛒", layout="wide")
st.title("🛒 Order-Status Funnel")
st.caption("SQL: `sql/08_order_status_funnel.sql`")
st.caption(
    "order_status is a terminal label, not an event log -- this funnel is built from the timestamp "
    "columns instead, which really do capture stage progression."
)

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)

funnel_query = f"""
WITH {cte},
scoped AS (
    SELECT o.order_approved_at, o.order_delivered_carrier_date, o.order_delivered_customer_date
    FROM orders o JOIN filtered_orders fo ON fo.order_id = o.order_id
),
stages AS (
    SELECT
        COUNT(*) AS purchased,
        SUM(CASE WHEN order_approved_at IS NOT NULL THEN 1 ELSE 0 END) AS approved,
        SUM(CASE WHEN order_delivered_carrier_date IS NOT NULL THEN 1 ELSE 0 END) AS shipped,
        SUM(CASE WHEN order_delivered_customer_date IS NOT NULL THEN 1 ELSE 0 END) AS delivered
    FROM scoped
)
SELECT 'purchased' AS stage, purchased AS orders, 100.0 AS pct_of_purchased, NULL AS pct_of_prior_stage FROM stages
UNION ALL
SELECT 'approved', approved, ROUND(100.0 * approved / purchased, 2), ROUND(100.0 * approved / purchased, 2) FROM stages
UNION ALL
SELECT 'shipped', shipped, ROUND(100.0 * shipped / purchased, 2), ROUND(100.0 * shipped / approved, 2) FROM stages
UNION ALL
SELECT 'delivered', delivered, ROUND(100.0 * delivered / purchased, 2), ROUND(100.0 * delivered / shipped, 2) FROM stages
"""

leakage_query = f"""
WITH {cte}
SELECT
    o.order_status,
    CASE
        WHEN o.order_delivered_carrier_date IS NOT NULL THEN 'reached_shipped'
        WHEN o.order_approved_at IS NOT NULL THEN 'reached_approved'
        ELSE 'never_approved'
    END AS furthest_stage_reached,
    COUNT(*) AS orders
FROM orders o
JOIN filtered_orders fo ON fo.order_id = o.order_id
WHERE o.order_status IN ('canceled', 'unavailable')
GROUP BY o.order_status, furthest_stage_reached
ORDER BY o.order_status, furthest_stage_reached
"""

with st.spinner("Building the order-status funnel..."):
    funnel_df = run_query(funnel_query, params)
    leakage_df = run_query(leakage_query, params)

if funnel_df.empty or funnel_df["orders"].iloc[0] == 0:
    st.info("No orders in the current filter selection.")
    st.stop()

kpi_row([
    ("Purchased", f"{int(funnel_df.loc[funnel_df.stage=='purchased','orders'].iloc[0]):,}"),
    ("Approved", f"{funnel_df.loc[funnel_df.stage=='approved','pct_of_purchased'].iloc[0]:.1f}% of purchased"),
    ("Shipped", f"{funnel_df.loc[funnel_df.stage=='shipped','pct_of_purchased'].iloc[0]:.1f}% of purchased"),
    ("Delivered", f"{funnel_df.loc[funnel_df.stage=='delivered','pct_of_purchased'].iloc[0]:.1f}% of purchased"),
])

st.divider()
fig = go.Figure(go.Funnel(
    y=funnel_df["stage"].str.capitalize(),
    x=funnel_df["orders"],
    marker={"color": [ORANGE, "#c9a227", "#8a8a8a", "#5a5a5a"]},
    textinfo="value+percent initial",
))
fig.update_layout(height=450)
st.plotly_chart(fig, use_container_width=True)
download_csv_button(funnel_df, "order_status_funnel.csv")

st.divider()
st.subheader("Where do canceled / unavailable orders get stuck?")
if leakage_df.empty:
    st.info("No canceled/unavailable orders in the current filter selection.")
else:
    st.dataframe(leakage_df, use_container_width=True, hide_index=True)
    download_csv_button(leakage_df, "order_status_leakage.csv")

st.info(
    "**So what:** on the full dataset, `unavailable` orders are 100% stuck at 'approved but never "
    "shipped' -- a stock/inventory signal, not a payment problem. `canceled` orders spread across every "
    "stage, with the largest share (65%) canceled after approval but before shipping -- pointing at the "
    "fulfillment gap between payment and dispatch as the place to investigate first.",
    icon="💡",
)
