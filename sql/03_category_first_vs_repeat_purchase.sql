-- Q3: Which product categories drive first purchases vs repeat purchases?
--
-- Grain: order_item (an order can contain multiple categories, so this counts
-- items, not orders -- a category's share here is "share of items bought by
-- first-time vs. repeat customers", not "share of orders"). order_seq comes
-- from the same customer_unique_id / order_purchase_timestamp ranking as Q2.
-- Categories are translated to English via product_category_name_translation;
-- rows with no translation keep the original Portuguese name.

WITH customer_orders AS (
    SELECT
        c.customer_unique_id,
        o.order_id,
        ROW_NUMBER() OVER (
            PARTITION BY c.customer_unique_id
            ORDER BY o.order_purchase_timestamp
        ) AS order_seq
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
),
items_with_category AS (
    SELECT
        co.order_seq,
        COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category
    FROM customer_orders co
    JOIN order_items oi ON oi.order_id = co.order_id
    JOIN products p ON p.product_id = oi.product_id
    LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
),
tagged AS (
    SELECT
        category,
        CASE WHEN order_seq = 1 THEN 'first_purchase' ELSE 'repeat_purchase' END AS purchase_type
    FROM items_with_category
),
totals AS (
    SELECT purchase_type, COUNT(*) AS total_items
    FROM tagged
    GROUP BY purchase_type
)
SELECT
    tg.category,
    tg.purchase_type,
    COUNT(*) AS item_count,
    ROUND(100.0 * COUNT(*) / t.total_items, 2) AS pct_of_purchase_type
FROM tagged tg
JOIN totals t ON t.purchase_type = tg.purchase_type
GROUP BY tg.category, tg.purchase_type
ORDER BY tg.purchase_type, item_count DESC;
