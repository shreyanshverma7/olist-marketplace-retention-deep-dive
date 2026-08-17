-- Q2: Repeat-purchase rate, and average/median time between 1st and 2nd purchase
--
-- Grain: customer_unique_id (see Q1 note on why customer_id can't be used here).
-- Denominator for the repeat-purchase rate is every distinct customer who
-- placed at least one order -- not just customers who show up more than once,
-- which would make the rate trivially 100%.

WITH customer_orders AS (
    SELECT
        c.customer_unique_id,
        o.order_id,
        o.order_purchase_timestamp,
        ROW_NUMBER() OVER (
            PARTITION BY c.customer_unique_id
            ORDER BY o.order_purchase_timestamp
        ) AS order_seq,
        LAG(o.order_purchase_timestamp) OVER (
            PARTITION BY c.customer_unique_id
            ORDER BY o.order_purchase_timestamp
        ) AS prev_order_ts
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
),
per_customer AS (
    SELECT
        customer_unique_id,
        MAX(order_seq) AS total_orders
    FROM customer_orders
    GROUP BY customer_unique_id
),
second_order_gap AS (
    SELECT
        customer_unique_id,
        (julianday(order_purchase_timestamp) - julianday(prev_order_ts)) AS days_to_second_order
    FROM customer_orders
    WHERE order_seq = 2
)
SELECT
    (SELECT COUNT(*) FROM per_customer) AS total_customers,
    (SELECT COUNT(*) FROM per_customer WHERE total_orders >= 2) AS repeat_customers,
    ROUND(
        100.0 * (SELECT COUNT(*) FROM per_customer WHERE total_orders >= 2)
        / (SELECT COUNT(*) FROM per_customer),
        2
    ) AS repeat_purchase_rate_pct,
    ROUND((SELECT AVG(days_to_second_order) FROM second_order_gap), 1) AS avg_days_to_2nd_order,
    -- median via the standard "middle row(s) of the sorted set" trick
    (
        SELECT ROUND(AVG(days_to_second_order), 1)
        FROM (
            SELECT days_to_second_order,
                   ROW_NUMBER() OVER (ORDER BY days_to_second_order) AS rn,
                   COUNT(*) OVER () AS cnt
            FROM second_order_gap
        )
        WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)
    ) AS median_days_to_2nd_order;
