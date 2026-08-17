-- Q1: Monthly cohort retention triangle
-- Do customers come back over time, and does retention differ by signup cohort?
--
-- Grain: customer_unique_id (the real person). customer_id is re-generated
-- per order in this schema, so grouping by it would make every customer look
-- like a one-time buyer.
--
-- Cohort = the calendar month of a customer's first-ever order, based on ALL
-- of their orders regardless of fulfillment status (a canceled/unavailable
-- order is still a customer action and evidence they returned).
--
-- Cohorts are restricted to 2017-01 through 2018-08: 2016-09/10/12 are a
-- near-empty pilot period (329 orders total) and 2018-09/10 are a near-empty
-- tail (20 orders) where the data collection window ends mid-stream -- both
-- would distort a retention triangle if included as cohorts.
--
-- CAVEAT: this dataset's last order is 2018-10-17, so later cohorts have less
-- time to show a repeat purchase than earlier ones (right-censoring). Only
-- compare cohorts at the same month_number, and prefer cohorts with a full
-- observation window for that month_number (see months_observable below).

WITH first_purchase AS (
    SELECT
        c.customer_unique_id,
        MIN(o.order_purchase_timestamp) AS first_order_ts
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
    GROUP BY c.customer_unique_id
),
cohorts AS (
    SELECT
        customer_unique_id,
        strftime('%Y-%m', first_order_ts) AS cohort_month
    FROM first_purchase
    WHERE first_order_ts >= '2017-01-01' AND first_order_ts < '2018-09-01'
),
customer_orders AS (
    SELECT
        c.customer_unique_id,
        o.order_purchase_timestamp
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
),
activity AS (
    SELECT
        coh.cohort_month,
        co.customer_unique_id,
        -- months between this order and the cohort's first-order month
        (CAST(strftime('%Y', co.order_purchase_timestamp) AS INT) - CAST(substr(coh.cohort_month, 1, 4) AS INT)) * 12
            + (CAST(strftime('%m', co.order_purchase_timestamp) AS INT) - CAST(substr(coh.cohort_month, 6, 2) AS INT))
            AS month_number
    FROM customer_orders co
    JOIN cohorts coh ON coh.customer_unique_id = co.customer_unique_id
),
cohort_sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size
    FROM cohorts
    GROUP BY cohort_month
),
triangle AS (
    SELECT
        cohort_month,
        month_number,
        COUNT(DISTINCT customer_unique_id) AS active_customers
    FROM activity
    GROUP BY cohort_month, month_number
)
SELECT
    t.cohort_month,
    cs.cohort_size,
    t.month_number,
    t.active_customers,
    ROUND(100.0 * t.active_customers / cs.cohort_size, 2) AS retention_pct,
    -- full months of data available for this cohort before the dataset ends (2018-08 inclusive)
    (2018 - CAST(substr(t.cohort_month, 1, 4) AS INT)) * 12
        + (8 - CAST(substr(t.cohort_month, 6, 2) AS INT)) AS months_observable
FROM triangle t
JOIN cohort_sizes cs ON cs.cohort_month = t.cohort_month
ORDER BY t.cohort_month, t.month_number;
