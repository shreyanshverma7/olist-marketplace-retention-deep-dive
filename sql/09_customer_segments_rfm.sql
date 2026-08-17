-- Q9: Customer segmentation adapted from RFM (Recency/Frequency/Monetary)
--
-- Standard 5-way NTILE(5) frequency-quintile scoring does not fit this
-- dataset honestly: frequency is degenerate here (96.9% of customers have
-- exactly 1 order, per the verified 3.12% repeat-purchase rate in
-- sql/02_repeat_purchase_rate_and_time_to_second_order.sql), so a quintile
-- split on frequency would just be arbitrary noise, not signal.
--
-- Adapted design instead:
--   1. A real, meaningful frequency split: repeat (2+ orders) vs. one-time.
--   2. Within one-time customers (the overwhelming majority), a monetary
--      tercile x recency-half split -- computed only within the one-time
--      population, so it isn't diluted by repeat customers' typically higher
--      spend.
--   3. Repeat customers are reported as their own segment given the small n
--      (2,997) relative to one-time customers (93,099).
--
-- Monetary = sum of delivered-order revenue (price + freight). Recency =
-- last order date, split at the median within the one-time population (a
-- self-calibrating 50/50 split rather than an arbitrary fixed date).

WITH order_revenue AS (
    SELECT order_id, SUM(price + freight_value) AS revenue FROM order_items GROUP BY order_id
),
customer_agg AS (
    SELECT
        cos.customer_unique_id,
        MAX(cos.order_seq) AS frequency,
        MAX(o.order_purchase_timestamp) AS last_order_ts,
        SUM(CASE WHEN o.order_status = 'delivered' THEN COALESCE(orv.revenue, 0) ELSE 0 END) AS monetary
    FROM customer_order_seq cos
    JOIN orders o ON o.order_id = cos.order_id
    LEFT JOIN order_revenue orv ON orv.order_id = cos.order_id
    GROUP BY cos.customer_unique_id
),
one_time_scored AS (
    SELECT
        customer_unique_id, monetary, last_order_ts,
        NTILE(3) OVER (ORDER BY monetary) AS monetary_tercile,
        NTILE(2) OVER (ORDER BY last_order_ts) AS recency_half
    FROM customer_agg WHERE frequency = 1
),
segmented AS (
    SELECT
        customer_unique_id, monetary,
        'Repeat customers' AS segment
    FROM customer_agg WHERE frequency >= 2
    UNION ALL
    SELECT
        customer_unique_id, monetary,
        (CASE monetary_tercile WHEN 1 THEN 'One-time: Low value' WHEN 2 THEN 'One-time: Mid value' ELSE 'One-time: High value' END)
        || ' / ' ||
        (CASE recency_half WHEN 1 THEN 'Lapsed' ELSE 'Recent' END) AS segment
    FROM one_time_scored
)
SELECT
    segment,
    COUNT(*) AS customers,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM customer_agg), 2) AS pct_of_customers,
    ROUND(AVG(monetary), 2) AS avg_monetary,
    ROUND(SUM(monetary), 2) AS total_monetary,
    ROUND(100.0 * SUM(monetary) / (SELECT SUM(monetary) FROM customer_agg), 2) AS pct_of_revenue
FROM segmented
GROUP BY segment
ORDER BY total_monetary DESC;
