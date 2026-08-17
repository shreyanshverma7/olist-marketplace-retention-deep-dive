-- Q4: Does late delivery predict bad reviews?
--
-- Restricted to delivered orders with a review (order_delivered_customer_date
-- and review_score both present) -- an order that was never delivered can't
-- have a delivery time, and one without a review has no score to compare.
-- "Late" is defined against Olist's own promise (order_estimated_delivery_date),
-- not an arbitrary day threshold, since promised delivery windows vary a lot
-- by region.
--
-- This file returns two result sets: a bucketed table (run first), then a
-- single-row Pearson correlation between delivery days and review score
-- (run second). Run them as separate statements against the same filtered set.

WITH scored_orders AS (
    SELECT
        o.order_id,
        r.review_score,
        julianday(o.order_delivered_customer_date) - julianday(o.order_purchase_timestamp) AS delivery_days,
        CASE
            WHEN o.order_delivered_customer_date <= o.order_estimated_delivery_date THEN 'on_time'
            ELSE 'late'
        END AS on_time_flag
    FROM orders o
    JOIN order_reviews r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
)
-- Result set 1: bucketed delivery time vs. review outcomes
SELECT
    CASE
        WHEN delivery_days < 7 THEN '1: <7 days'
        WHEN delivery_days < 14 THEN '2: 7-13 days'
        WHEN delivery_days < 21 THEN '3: 14-20 days'
        WHEN delivery_days < 30 THEN '4: 21-29 days'
        ELSE '5: 30+ days'
    END AS delivery_bucket,
    on_time_flag,
    COUNT(*) AS orders,
    ROUND(AVG(review_score), 2) AS avg_review_score,
    ROUND(100.0 * SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_bad_review
FROM scored_orders
GROUP BY delivery_bucket, on_time_flag
ORDER BY delivery_bucket, on_time_flag;

-- Result set 2: Pearson correlation between delivery_days and review_score
-- (SQLite has no built-in CORR(), so this spells out the formula:
--  r = (n*Sxy - Sx*Sy) / sqrt((n*Sxx - Sx^2) * (n*Syy - Sy^2)) )
WITH scored_orders AS (
    SELECT
        julianday(o.order_delivered_customer_date) - julianday(o.order_purchase_timestamp) AS delivery_days,
        r.review_score
    FROM orders o
    JOIN order_reviews r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
),
sums AS (
    SELECT
        COUNT(*) AS n,
        SUM(delivery_days) AS sx,
        SUM(review_score) AS sy,
        SUM(delivery_days * review_score) AS sxy,
        SUM(delivery_days * delivery_days) AS sxx,
        SUM(review_score * review_score) AS syy
    FROM scored_orders
)
SELECT
    n,
    ROUND(
        (n * sxy - sx * sy)
        / (
            SQRT(n * sxx - sx * sx) * SQRT(n * syy - sy * sy)
        ),
        4
    ) AS pearson_r
FROM sums;
