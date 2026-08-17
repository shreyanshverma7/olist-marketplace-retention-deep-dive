-- Q7: Freight cost concentration by region -- which seller states are
-- structurally disadvantaged by shipping cost, and does that relate to
-- review scores?
--
-- Grain: order_item, attributed to the seller's state (freight cost is driven
-- primarily by the seller-to-customer shipping distance, so seller_state is
-- the natural "region" for this question). freight_ratio = freight_value /
-- price, i.e. shipping cost as a fraction of the item's own price -- a R$20
-- freight charge means very different things on a R$30 item vs. a R$300 one,
-- so the ratio is the comparable unit, not the raw freight value.
-- Only delivered orders with a review are included, so the review-score join
-- doesn't silently drop denominator rows for undelivered orders.

WITH item_freight AS (
    SELECT
        s.seller_state,
        oi.order_id,
        oi.price,
        oi.freight_value,
        oi.freight_value / oi.price AS freight_ratio,
        r.review_score
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    JOIN sellers s ON s.seller_id = oi.seller_id
    JOIN order_reviews r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND oi.price > 0
)
SELECT
    seller_state,
    COUNT(*) AS items,
    ROUND(AVG(price), 2) AS avg_price_brl,
    ROUND(AVG(freight_value), 2) AS avg_freight_brl,
    ROUND(AVG(freight_ratio), 4) AS avg_freight_ratio,
    ROUND(AVG(review_score), 2) AS avg_review_score,
    ROUND(100.0 * SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_bad_review
FROM item_freight
GROUP BY seller_state
HAVING COUNT(*) >= 30  -- drop states with too few items to read a rate from
ORDER BY avg_freight_ratio DESC;
