-- Q8: Order-status funnel -- where do orders leak, and where do
-- cancellations/unavailability concentrate?
--
-- order_status is a terminal label, not an event log, so a defensible funnel
-- is built from the timestamp columns instead, which really do capture stage
-- progression: order_purchase_timestamp (100%, every order) ->
-- order_approved_at present (approved) -> order_delivered_carrier_date
-- present (shipped) -> order_delivered_customer_date present (delivered).
-- This file returns two result sets: the funnel itself, then a breakdown of
-- where canceled/unavailable orders got stuck. Run as separate statements.

-- Result set 1: stage-over-stage funnel
WITH stages AS (
    SELECT
        COUNT(*) AS purchased,
        SUM(CASE WHEN order_approved_at IS NOT NULL THEN 1 ELSE 0 END) AS approved,
        SUM(CASE WHEN order_delivered_carrier_date IS NOT NULL THEN 1 ELSE 0 END) AS shipped,
        SUM(CASE WHEN order_delivered_customer_date IS NOT NULL THEN 1 ELSE 0 END) AS delivered
    FROM orders
)
SELECT 'purchased' AS stage, purchased AS orders, 100.0 AS pct_of_purchased, NULL AS pct_of_prior_stage FROM stages
UNION ALL
SELECT 'approved', approved, ROUND(100.0 * approved / purchased, 2), ROUND(100.0 * approved / purchased, 2) FROM stages
UNION ALL
SELECT 'shipped', shipped, ROUND(100.0 * shipped / purchased, 2), ROUND(100.0 * shipped / approved, 2) FROM stages
UNION ALL
SELECT 'delivered', delivered, ROUND(100.0 * delivered / purchased, 2), ROUND(100.0 * delivered / shipped, 2) FROM stages;

-- Result set 2: where canceled/unavailable orders got stuck
SELECT
    order_status,
    CASE
        WHEN order_delivered_carrier_date IS NOT NULL THEN 'reached_shipped'
        WHEN order_approved_at IS NOT NULL THEN 'reached_approved'
        ELSE 'never_approved'
    END AS furthest_stage_reached,
    COUNT(*) AS orders
FROM orders
WHERE order_status IN ('canceled', 'unavailable')
GROUP BY order_status, furthest_stage_reached
ORDER BY order_status, furthest_stage_reached;
