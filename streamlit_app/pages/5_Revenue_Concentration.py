"""Q5: Revenue concentration -- Pareto/Lorenz curves for customers and sellers."""

import plotly.graph_objects as go
import streamlit as st
from common import (
    ORANGE,
    filtered_orders_cte,
    kpi_row,
    render_global_filters,
    run_query,
)

st.set_page_config(page_title="Revenue Concentration", page_icon=":bar_chart:", layout="wide")
st.title("Revenue Concentration: Customers vs. Sellers")
st.caption("SQL: `sql/05_revenue_concentration_pareto_customers_sellers.sql`")

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)


def lorenz_query(entity_col: str, entity_join: str) -> str:
    return f"""
    WITH {cte},
    revenue AS (
        SELECT {entity_col} AS entity, SUM(oi.price + oi.freight_value) AS revenue
        FROM orders o
        JOIN filtered_orders fo ON fo.order_id = o.order_id
        JOIN order_items oi ON oi.order_id = o.order_id
        {entity_join}
        WHERE o.order_status = 'delivered'
        GROUP BY entity
    ),
    ranked AS (
        SELECT entity, revenue,
               ROW_NUMBER() OVER (ORDER BY revenue DESC) AS rnk,
               COUNT(*) OVER () AS total_n,
               SUM(revenue) OVER () AS total_rev
        FROM revenue
    )
    SELECT rnk,
           100.0 * rnk / total_n AS cum_pct_population,
           100.0 * SUM(revenue) OVER (ORDER BY revenue DESC ROWS UNBOUNDED PRECEDING) / total_rev AS cum_pct_revenue
    FROM ranked ORDER BY rnk
    """


cust_df = run_query(
    lorenz_query("c.customer_unique_id", "JOIN customers c ON c.customer_id = o.customer_id"), params
)
seller_df = run_query(lorenz_query("oi.seller_id", ""), params)

if cust_df.empty or seller_df.empty:
    st.info("No delivered revenue in the current filter selection.")
    st.stop()


def top_n_pct(df, pct):
    """Exact breakpoint (matches sql/05's rnk = round(pct/100 * total_n)), not a
    nearest-point lookup on the curve -- the latter drifts from the verified
    SQL output and would make the dashboard disagree with the README."""
    total_n = int(df["rnk"].max())
    target_rnk = min(max(round(pct / 100 * total_n), 1), total_n)
    return df.loc[df["rnk"] == target_rnk, "cum_pct_revenue"].values[0]


kpi_row([
    ("Top 5% customers = ", f"{top_n_pct(cust_df, 5):.1f}% of GMV"),
    ("Top 5% sellers = ", f"{top_n_pct(seller_df, 5):.1f}% of GMV"),
    ("Top 20% customers = ", f"{top_n_pct(cust_df, 20):.1f}% of GMV"),
    ("Top 20% sellers = ", f"{top_n_pct(seller_df, 20):.1f}% of GMV"),
])

st.divider()
fig = go.Figure()
fig.add_trace(go.Scatter(x=[0, 100], y=[0, 100], mode="lines", name="Perfect equality",
                          line={"dash": "dash", "color": "#666"}))
fig.add_trace(go.Scatter(x=cust_df["cum_pct_population"], y=cust_df["cum_pct_revenue"],
                          mode="lines", name="Customers", line={"color": "#3a3a3a", "width": 3}))
fig.add_trace(go.Scatter(x=seller_df["cum_pct_population"], y=seller_df["cum_pct_revenue"],
                          mode="lines", name="Sellers", line={"color": ORANGE, "width": 3}))
fig.update_layout(
    xaxis_title="Cumulative % of customers/sellers (ranked by revenue, highest first)",
    yaxis_title="Cumulative % of GMV", height=500,
)
st.plotly_chart(fig, use_container_width=True)
st.caption(
    "The further a curve bows from the diagonal, the more concentrated revenue is. The seller curve "
    "bowing further than the customer curve means the marketplace depends more heavily on its top sellers "
    "than on its top customers."
)
