-- Q5: Revenue concentration -- Pareto of customers and of sellers
--
-- Revenue = order_items.price + order_items.freight_value (GMV) on delivered
-- orders only, matching how "revenue" is used everywhere else in this project
-- (cancelled/unavailable orders never generated real revenue).
-- Grain is customer_unique_id for the customer curve (see Q1), seller_id for
-- the seller curve. Each result set is a full Lorenz-curve table: one row per
-- customer/seller ranked by revenue descending, with cumulative % of revenue
-- and cumulative % of the customer/seller population -- enough to plot the
-- curve and to read off "top N% of customers/sellers = X% of revenue" at any
-- breakpoint. Run the two statements as separate result sets.

-- Result set 1: customer revenue Pareto
WITH customer_revenue AS (
    SELECT
        c.customer_unique_id,
        SUM(oi.price + oi.freight_value) AS revenue
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id
),
ranked AS (
    SELECT
        customer_unique_id,
        revenue,
        ROW_NUMBER() OVER (ORDER BY revenue DESC) AS rnk,
        COUNT(*) OVER () AS total_customers,
        SUM(revenue) OVER () AS total_revenue
    FROM customer_revenue
)
SELECT
    rnk,
    customer_unique_id,
    revenue,
    ROUND(100.0 * rnk / total_customers, 4) AS cumulative_pct_customers,
    ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC ROWS UNBOUNDED PRECEDING) / total_revenue, 4) AS cumulative_pct_revenue
FROM ranked
ORDER BY rnk;

-- Result set 2: seller revenue Pareto
WITH seller_revenue AS (
    SELECT
        oi.seller_id,
        SUM(oi.price + oi.freight_value) AS revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY oi.seller_id
),
ranked AS (
    SELECT
        seller_id,
        revenue,
        ROW_NUMBER() OVER (ORDER BY revenue DESC) AS rnk,
        COUNT(*) OVER () AS total_sellers,
        SUM(revenue) OVER () AS total_revenue
    FROM seller_revenue
)
SELECT
    rnk,
    seller_id,
    revenue,
    ROUND(100.0 * rnk / total_sellers, 4) AS cumulative_pct_sellers,
    ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC ROWS UNBOUNDED PRECEDING) / total_revenue, 4) AS cumulative_pct_revenue
FROM ranked
ORDER BY rnk;
