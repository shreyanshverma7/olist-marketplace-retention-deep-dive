"""Q6: Payment installments/type vs. order value and repeat-purchase behavior."""

import plotly.express as px
import streamlit as st
from common import (
    PAYMENT_TYPE_COLORS,
    download_csv_button,
    filtered_orders_cte,
    render_global_filters,
    run_query,
)

st.set_page_config(page_title="Payments and Installments", page_icon="💳", layout="wide")
st.title("💳 Payments & Installments")
st.caption("SQL: `sql/06_payment_installments_vs_order_value_and_repeat.sql`")

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)

value_query = f"""
WITH {cte},
ranked_payments AS (
    SELECT op.order_id, op.payment_type, op.payment_value, op.payment_installments,
           ROW_NUMBER() OVER (PARTITION BY op.order_id ORDER BY op.payment_value DESC) AS rnk
    FROM order_payments op
    JOIN filtered_orders fo ON fo.order_id = op.order_id
),
agg AS (
    SELECT order_id, SUM(payment_value) AS order_value, MAX(payment_installments) AS max_inst,
           MAX(CASE WHEN rnk = 1 THEN payment_type END) AS primary_type
    FROM ranked_payments GROUP BY order_id
)
SELECT
    CASE
        WHEN max_inst = 1 THEN '1: single'
        WHEN max_inst BETWEEN 2 AND 3 THEN '2: 2-3'
        WHEN max_inst BETWEEN 4 AND 6 THEN '3: 4-6'
        WHEN max_inst BETWEEN 7 AND 10 THEN '4: 7-10'
        ELSE '5: 11+'
    END AS installment_bucket,
    primary_type, COUNT(*) AS orders, ROUND(AVG(order_value), 2) AS avg_value
FROM agg WHERE primary_type IS NOT NULL AND primary_type != 'not_defined'
GROUP BY installment_bucket, primary_type
"""
with st.spinner("Analyzing payments..."):
    value_df = run_query(value_query, params)

# order_seq comes from the precomputed customer_order_seq table (see
# database/build_olist_db.py) -- no ROW_NUMBER() recomputation here.
repeat_query = f"""
WITH {cte},
ranked_payments AS (
    SELECT op.order_id, op.payment_type,
           ROW_NUMBER() OVER (PARTITION BY op.order_id ORDER BY op.payment_value DESC) AS rnk
    FROM order_payments op JOIN filtered_orders fo ON fo.order_id = op.order_id
),
agg AS (SELECT order_id, MAX(CASE WHEN rnk = 1 THEN payment_type END) AS primary_type FROM ranked_payments GROUP BY order_id),
customer_orders AS (
    SELECT cos.customer_unique_id, cos.order_id, cos.order_seq
    FROM customer_order_seq cos
    JOIN filtered_orders fo2 ON fo2.order_id = cos.order_id
),
-- COUNT(*), not MAX(order_seq): total_orders must be "how many of this
-- customer's orders pass the current filter", not their global order count.
per_customer AS (SELECT customer_unique_id, COUNT(*) AS total_orders FROM customer_orders GROUP BY customer_unique_id),
first_order_type AS (
    SELECT co.customer_unique_id, a.primary_type
    FROM customer_orders co JOIN agg a ON a.order_id = co.order_id
    WHERE co.order_seq = 1 AND a.primary_type IS NOT NULL AND a.primary_type != 'not_defined'
)
SELECT fot.primary_type, COUNT(*) AS customers,
       ROUND(100.0 * SUM(CASE WHEN pc.total_orders >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS repeat_rate
FROM first_order_type fot JOIN per_customer pc ON pc.customer_unique_id = fot.customer_unique_id
GROUP BY fot.primary_type
"""
repeat_df = run_query(repeat_query, params)

if value_df.empty:
    st.info("No payments in the current filter selection.")
    st.stop()

labels = {
    "installment_bucket": "Installment count",
    "avg_value": "Avg order value (R$)",
    "primary_type": "Payment type",
    "repeat_rate": "Repeat-purchase rate (%)",
}

col1, col2 = st.columns(2)
with col1:
    st.subheader("Avg order value by installment count")
    fig1 = px.bar(
        value_df, x="installment_bucket", y="avg_value", color="primary_type", barmode="group",
        color_discrete_map=PAYMENT_TYPE_COLORS, labels=labels,
    )
    st.plotly_chart(fig1, use_container_width=True)
with col2:
    st.subheader("Repeat-purchase rate by first-order payment type")
    fig2 = px.bar(
        repeat_df, x="primary_type", y="repeat_rate", color="primary_type",
        color_discrete_map=PAYMENT_TYPE_COLORS, labels=labels,
    )
    fig2.update_layout(showlegend=False)
    st.plotly_chart(fig2, use_container_width=True)

st.info(
    "**So what:** order value scales cleanly with installment count (R$103 for a single payment vs. "
    "R$373+ for 11+ installments), but repeat-purchase rate is roughly flat across payment types -- "
    "payment method is not a lever for retention, it's a lever for average order value.",
    icon="💡",
)
col1, col2 = st.columns(2)
with col1:
    download_csv_button(value_df, "payments_order_value.csv")
with col2:
    download_csv_button(repeat_df, "payments_repeat_rate.csv")
