"""Q3: Which categories drive first purchases vs. repeat purchases -- with a
category-to-cohort drill-down."""

import plotly.express as px
import streamlit as st
from common import (
    ORANGE,
    download_csv_button,
    filtered_orders_cte,
    render_global_filters,
    run_query,
)

st.set_page_config(page_title="Category Drilldown", page_icon="🏷️", layout="wide")
st.title("🏷️ Category Mix: First vs. Repeat Purchases")
st.caption("SQL: `sql/03_category_first_vs_repeat_purchase.sql`")

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)

# order_seq comes from the precomputed customer_order_seq table (see
# database/build_olist_db.py) -- no ROW_NUMBER() recomputation here.
mix_query = f"""
WITH {cte},
customer_orders AS (
    SELECT cos.customer_unique_id, cos.order_id, cos.order_seq
    FROM customer_order_seq cos
    JOIN filtered_orders fo ON fo.order_id = cos.order_id
),
items AS (
    SELECT co.order_seq, COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category
    FROM customer_orders co
    JOIN order_items oi ON oi.order_id = co.order_id
    JOIN products p ON p.product_id = oi.product_id
    LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
),
tagged AS (SELECT category, CASE WHEN order_seq = 1 THEN 'first_purchase' ELSE 'repeat_purchase' END AS purchase_type FROM items),
totals AS (SELECT purchase_type, COUNT(*) AS total FROM tagged GROUP BY purchase_type)
SELECT tg.category, tg.purchase_type, COUNT(*) AS item_count,
       ROUND(100.0 * COUNT(*) / t.total, 2) AS pct_of_purchase_type
FROM tagged tg JOIN totals t ON t.purchase_type = tg.purchase_type
GROUP BY tg.category, tg.purchase_type
"""
with st.spinner("Computing category mix..."):
    df = run_query(mix_query, params)

if df.empty:
    st.info("No items in the current filter selection.")
    st.stop()

top15 = df.groupby("category")["item_count"].sum().nlargest(15).index
plot_df = df[df["category"].isin(top15)]
fig = px.bar(
    plot_df, x="category", y="pct_of_purchase_type", color="purchase_type", barmode="group",
    color_discrete_map={"first_purchase": "#3a3a3a", "repeat_purchase": ORANGE},
    labels={
        "pct_of_purchase_type": "% of that purchase type's items",
        "category": "Category",
        "purchase_type": "Purchase type",
    },
)
fig.update_layout(xaxis_tickangle=-40, height=500)
st.plotly_chart(fig, use_container_width=True)
download_csv_button(df, "category_first_vs_repeat.csv")

st.divider()
st.subheader("Drill down: cohort retention for a category's first-time buyers")
st.caption(
    "Pick a category to see the retention triangle for customers whose *first-ever* purchase "
    "included an item in that category."
)
category_options = sorted(df["category"].unique())
# Default to the highest-volume category (by total items across both purchase
# types) rather than the alphabetically-first one, which is often a niche
# category too small to read a repeat rate from.
default_category = df.groupby("category")["item_count"].sum().idxmax()
default_index = category_options.index(default_category) if default_category in category_options else 0
category_choice = st.selectbox("Category", category_options, index=default_index)

drilldown_query = f"""
WITH {cte},
customer_orders AS (
    SELECT cos.customer_unique_id, cos.order_id, cos.order_seq
    FROM customer_order_seq cos
    JOIN filtered_orders fo ON fo.order_id = cos.order_id
),
first_orders AS (SELECT * FROM customer_orders WHERE order_seq = 1),
category_first_buyers AS (
    SELECT DISTINCT fo.customer_unique_id
    FROM first_orders fo
    JOIN order_items oi ON oi.order_id = fo.order_id
    JOIN products p ON p.product_id = oi.product_id
    LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
    WHERE COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') = ?
),
-- COUNT(*), not MAX(order_seq): total_orders must be "how many of this
-- customer's orders pass the current filter", not their global order count.
per_customer AS (SELECT customer_unique_id, COUNT(*) AS total_orders FROM customer_orders GROUP BY customer_unique_id)
SELECT
    COUNT(*) AS cohort_size,
    SUM(CASE WHEN pc.total_orders >= 2 THEN 1 ELSE 0 END) AS repeat_customers,
    ROUND(100.0 * SUM(CASE WHEN pc.total_orders >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS repeat_rate
FROM category_first_buyers cfb
JOIN per_customer pc ON pc.customer_unique_id = cfb.customer_unique_id
"""
dd = run_query(drilldown_query, params + (category_choice,)).iloc[0]

c1, c2, c3 = st.columns(3)
c1.metric(f"Customers whose first buy was '{category_choice}'", f"{int(dd['cohort_size']):,}")
c2.metric("Of those, became repeat customers", f"{int(dd['repeat_customers']):,}")
c3.metric("Repeat rate for this category", f"{dd['repeat_rate']:.2f}%")

st.info(
    "**So what:** `bed_bath_table` over-indexes hardest on repeat purchases of any major category -- "
    "9.68% of first-purchase items vs. 15.06% of repeat-purchase items -- making it a natural place to "
    "pilot a win-back campaign for first-time buyers.",
    icon="💡",
)
