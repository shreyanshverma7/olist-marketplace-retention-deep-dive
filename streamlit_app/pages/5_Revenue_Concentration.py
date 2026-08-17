"""Q5: Revenue concentration -- Pareto/Lorenz curves for customers and sellers."""

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

st.set_page_config(page_title="Revenue Concentration", page_icon="💰", layout="wide")
st.title("💰 Revenue Concentration: Customers vs. Sellers")
st.caption("SQL: `sql/05_revenue_concentration_pareto_customers_sellers.sql`")

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)


def lorenz_query(entity_col: str, entity_join: str) -> str:
    """The window-function ranking still has to scan every customer/seller to
    be correct, but the *output* doesn't need one row per entity for a
    visually smooth curve -- only ~300 evenly-spaced points, plus the exact
    5%/20% breakpoints (so the on-screen number is always an exact match, not
    a nearest-neighbor approximation) and the two curve endpoints. Cuts the
    returned payload from ~93k/~3k rows to a few hundred, which is most of
    what made this page's first load slow."""
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
    ),
    curve AS (
        SELECT rnk, total_n,
               100.0 * rnk / total_n AS cum_pct_population,
               100.0 * SUM(revenue) OVER (ORDER BY revenue DESC ROWS UNBOUNDED PRECEDING) / total_rev AS cum_pct_revenue
        FROM ranked
    )
    SELECT rnk, total_n, cum_pct_population, cum_pct_revenue
    FROM curve
    WHERE rnk = 1 OR rnk = total_n
       OR rnk = CAST(ROUND(0.05 * total_n) AS INT)
       OR rnk = CAST(ROUND(0.20 * total_n) AS INT)
       OR rnk % MAX(1, CAST(total_n / 300 AS INT)) = 0
    ORDER BY rnk
    """


with st.spinner("Ranking customers and sellers by revenue..."):
    cust_df = run_query(
        lorenz_query("c.customer_unique_id", "JOIN customers c ON c.customer_id = o.customer_id"), params
    )
    seller_df = run_query(lorenz_query("oi.seller_id", ""), params)

if cust_df.empty or seller_df.empty:
    st.info("No delivered revenue in the current filter selection.")
    st.stop()


def top_n_pct(df, pct):
    """Exact breakpoint (matches sql/05's rnk = round(pct/100 * total_n)) --
    guaranteed present in the downsampled df since the query above always
    includes the 5%/20% ranks explicitly, so this is never an approximation."""
    total_n = int(df["total_n"].iloc[0])
    target_rnk = min(max(round(pct / 100 * total_n), 1), total_n)
    return df.loc[df["rnk"] == target_rnk, "cum_pct_revenue"].values[0]


kpi_row([
    ("Top 5% customers = ", f"{top_n_pct(cust_df, 5):.1f}% of GMV",
     "Cumulative % of delivered GMV held by the top 5% of customers, ranked by revenue."),
    ("Top 5% sellers = ", f"{top_n_pct(seller_df, 5):.1f}% of GMV",
     "Cumulative % of delivered GMV held by the top 5% of sellers, ranked by revenue."),
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

st.info(
    "**So what:** the top 5% of sellers already account for roughly half of delivered GMV. Treat seller "
    "concentration as a platform risk -- a seller-retention/diversification program is a bigger structural "
    "priority than deepening the customer base, where revenue is comparatively well spread.",
    icon="💡",
)

col1, col2 = st.columns(2)
with col1:
    download_csv_button(cust_df, "revenue_concentration_customers.csv", "Download customer curve (CSV)")
with col2:
    download_csv_button(seller_df, "revenue_concentration_sellers.csv", "Download seller curve (CSV)")
