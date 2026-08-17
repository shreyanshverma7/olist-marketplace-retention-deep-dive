-- Q6: Do payment installments / payment type relate to order value and to
-- whether a customer comes back?
--
-- An order can have more than one order_payments row (e.g. part voucher,
-- part credit card), so payment is aggregated to one row per order first:
-- total value paid, the highest installment count used, and a "primary"
-- payment_type taken from the payment leg with the largest value. order_seq
-- (see Q2) tags whether this is a customer's first order or a repeat one.

WITH ranked_payments AS (
    SELECT
        order_id,
        payment_type,
        payment_value,
        ROW_NUMBER() OVER (
            PARTITION BY order_id ORDER BY payment_value DESC
        ) AS payment_rnk
    FROM order_payments
),
order_payment_agg AS (
    SELECT
        rp.order_id,
        SUM(op.payment_value) AS order_value,
        MAX(op.payment_installments) AS max_installments,
        MAX(CASE WHEN rp.payment_rnk = 1 THEN rp.payment_type END) AS primary_payment_type
    FROM ranked_payments rp
    JOIN order_payments op ON op.order_id = rp.order_id
    GROUP BY rp.order_id
),
customer_orders AS (
    SELECT
        c.customer_unique_id,
        o.order_id,
        ROW_NUMBER() OVER (
            PARTITION BY c.customer_unique_id
            ORDER BY o.order_purchase_timestamp
        ) AS order_seq
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
)
-- Result set 1: order value by installment bucket and payment type
SELECT
    CASE
        WHEN max_installments = 1 THEN '1: single payment'
        WHEN max_installments BETWEEN 2 AND 3 THEN '2: 2-3 installments'
        WHEN max_installments BETWEEN 4 AND 6 THEN '3: 4-6 installments'
        WHEN max_installments BETWEEN 7 AND 10 THEN '4: 7-10 installments'
        ELSE '5: 11+ installments'
    END AS installment_bucket,
    primary_payment_type,
    COUNT(*) AS orders,
    ROUND(AVG(order_value), 2) AS avg_order_value_brl
FROM order_payment_agg
GROUP BY installment_bucket, primary_payment_type
ORDER BY installment_bucket, orders DESC;

-- Result set 2: repeat-purchase rate by the payment type used on the FIRST order
WITH ranked_payments AS (
    SELECT
        order_id,
        payment_type,
        payment_value,
        ROW_NUMBER() OVER (
            PARTITION BY order_id ORDER BY payment_value DESC
        ) AS payment_rnk
    FROM order_payments
),
order_payment_agg AS (
    SELECT
        order_id,
        MAX(CASE WHEN payment_rnk = 1 THEN payment_type END) AS primary_payment_type
    FROM ranked_payments
    GROUP BY order_id
),
customer_orders AS (
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
per_customer AS (
    SELECT customer_unique_id, MAX(order_seq) AS total_orders
    FROM customer_orders
    GROUP BY customer_unique_id
),
first_order_payment AS (
    SELECT
        co.customer_unique_id,
        opa.primary_payment_type
    FROM customer_orders co
    JOIN order_payment_agg opa ON opa.order_id = co.order_id
    WHERE co.order_seq = 1
)
SELECT
    fop.primary_payment_type,
    COUNT(*) AS customers,
    SUM(CASE WHEN pc.total_orders >= 2 THEN 1 ELSE 0 END) AS repeat_customers,
    ROUND(100.0 * SUM(CASE WHEN pc.total_orders >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS repeat_purchase_rate_pct
FROM first_order_payment fop
JOIN per_customer pc ON pc.customer_unique_id = fop.customer_unique_id
GROUP BY fop.primary_payment_type
ORDER BY customers DESC;
