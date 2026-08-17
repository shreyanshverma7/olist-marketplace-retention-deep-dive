"""Statistical rigor pass, recomputed live against the current filter selection.

Mirrors analysis/statistical_tests.py's five tests and Holm-Bonferroni
correction, but scoped to whatever the sidebar filters are currently set to
-- narrowing the filters can (and does) change which results survive
correction, which is the point of making this page live rather than a static
table copied from the CLI script's output.
"""

import numpy as np
import pandas as pd
import streamlit as st
from common import (
    download_csv_button,
    filtered_orders_cte,
    render_global_filters,
    run_query,
)
from scipy import stats

st.set_page_config(page_title="Statistical Tests", page_icon="🧪", layout="wide")
st.title("🧪 Statistical Rigor Pass")
st.caption("Also runnable standalone: `python3 analysis/statistical_tests.py` (unfiltered, full dataset).")

filters = render_global_filters()
cte, params = filtered_orders_cte(filters)


def two_proportion_z_test(x1, n1, x2, n2):
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return z, p


def holm_bonferroni(pvals: dict, alpha=0.05):
    m = len(pvals)
    ordered = sorted(pvals.items(), key=lambda kv: kv[1])
    verdicts, blocked = {}, False
    for i, (name, p) in enumerate(ordered):
        threshold = alpha / (m - i)
        sig = (p <= threshold) and not blocked
        verdicts[name] = sig
        if not sig:
            blocked = True
    return verdicts


tests = {}

cat_query = f"""
WITH {cte},
customer_orders AS (
    SELECT cos.customer_unique_id, cos.order_id, cos.order_seq
    FROM customer_order_seq cos
    JOIN filtered_orders fo ON fo.order_id = cos.order_id
),
items AS (
    SELECT co.order_seq, COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category
    FROM customer_orders co JOIN order_items oi ON oi.order_id = co.order_id
    JOIN products p ON p.product_id = oi.product_id
    LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
),
top15 AS (SELECT category FROM items GROUP BY category ORDER BY COUNT(*) DESC LIMIT 15)
SELECT
    CASE WHEN category IN (SELECT category FROM top15) THEN category ELSE 'other' END AS category,
    CASE WHEN order_seq = 1 THEN 'first' ELSE 'repeat' END AS purchase_type,
    COUNT(*) AS n
FROM items GROUP BY 1, 2
"""
cat_df = run_query(cat_query, params)
if not cat_df.empty and cat_df["purchase_type"].nunique() == 2:
    table = cat_df.pivot(index="category", columns="purchase_type", values="n").fillna(0)
    if table.shape[0] >= 2:
        chi2, p, dof, _ = stats.chi2_contingency(table)
        tests["Category mix: first vs. repeat purchase items"] = {"stat": f"chi2={chi2:.2f}, dof={dof}", "p": p, "n": int(table.values.sum())}

delivery_query = f"""
WITH {cte}
SELECT
    CASE WHEN o.order_delivered_customer_date <= o.order_estimated_delivery_date THEN 'on_time' ELSE 'late' END AS flag,
    SUM(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) AS bad, COUNT(*) AS n
FROM orders o
JOIN order_reviews r ON r.order_id = o.order_id
JOIN filtered_orders fo ON fo.order_id = o.order_id
WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
GROUP BY flag
"""
delivery_df = run_query(delivery_query, params).set_index("flag")
if {"late", "on_time"}.issubset(delivery_df.index):
    z, p = two_proportion_z_test(
        delivery_df.loc["late", "bad"], delivery_df.loc["late", "n"],
        delivery_df.loc["on_time", "bad"], delivery_df.loc["on_time", "n"],
    )
    tests["Bad-review rate: late vs. on-time delivery"] = {"stat": f"z={z:.2f}", "p": p, "n": int(delivery_df["n"].sum())}

corr_query = f"""
WITH {cte}
SELECT julianday(o.order_delivered_customer_date) - julianday(o.order_purchase_timestamp) AS delivery_days, r.review_score
FROM orders o JOIN order_reviews r ON r.order_id = o.order_id
JOIN filtered_orders fo ON fo.order_id = o.order_id
WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
"""
corr_df = run_query(corr_query, params)
if len(corr_df) >= 3:
    r, p = stats.pearsonr(corr_df["delivery_days"], corr_df["review_score"])
    tests["Correlation: delivery days vs. review score"] = {"stat": f"r={r:.4f}", "p": p, "n": len(corr_df)}

payment_query = f"""
WITH {cte},
ranked_payments AS (
    SELECT op.order_id, op.payment_type,
           ROW_NUMBER() OVER (PARTITION BY op.order_id ORDER BY op.payment_value DESC) AS rnk
    FROM order_payments op JOIN filtered_orders fo ON fo.order_id = op.order_id
),
agg AS (SELECT order_id, MAX(CASE WHEN rnk = 1 THEN payment_type END) AS primary_type FROM ranked_payments GROUP BY order_id),
customer_orders AS (
    SELECT cos.customer_unique_id, cos.order_id, cos.order_seq
    FROM customer_order_seq cos
    JOIN filtered_orders fo2 ON fo2.order_id = cos.order_id
),
-- COUNT(*), not MAX(order_seq): total_orders must be "how many of this
-- customer's orders pass the current filter", not their global order count.
per_customer AS (SELECT customer_unique_id, COUNT(*) AS total_orders FROM customer_orders GROUP BY customer_unique_id),
first_order_type AS (
    SELECT co.customer_unique_id, a.primary_type
    FROM customer_orders co JOIN agg a ON a.order_id = co.order_id
    WHERE co.order_seq = 1 AND a.primary_type IN ('credit_card','boleto','voucher','debit_card')
)
SELECT fot.primary_type AS payment_type,
       CASE WHEN pc.total_orders >= 2 THEN 'repeat' ELSE 'one_time' END AS status,
       COUNT(*) AS n
FROM first_order_type fot JOIN per_customer pc ON pc.customer_unique_id = fot.customer_unique_id
GROUP BY 1, 2
"""
payment_df = run_query(payment_query, params)
if not payment_df.empty and payment_df["status"].nunique() == 2:
    table = payment_df.pivot(index="payment_type", columns="status", values="n").fillna(0)
    if table.shape[0] >= 2:
        chi2, p, dof, _ = stats.chi2_contingency(table)
        tests["Repeat-customer rate by first-order payment type"] = {"stat": f"chi2={chi2:.2f}, dof={dof}", "p": p, "n": int(table.values.sum())}

freight_query = f"""
WITH {cte},
item_freight AS (
    SELECT s.seller_state, oi.freight_value / oi.price AS freight_ratio, r.review_score
    FROM orders o
    JOIN filtered_orders fo ON fo.order_id = o.order_id
    JOIN order_items oi ON oi.order_id = o.order_id
    JOIN sellers s ON s.seller_id = oi.seller_id
    JOIN order_reviews r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered' AND oi.price > 0
)
SELECT seller_state, AVG(freight_ratio) AS avg_freight_ratio,
       100.0 * SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END) / COUNT(*) AS pct_bad_review, COUNT(*) AS n
FROM item_freight GROUP BY seller_state HAVING COUNT(*) >= 30
"""
freight_df = run_query(freight_query, params)
if len(freight_df) >= 3:
    r, p = stats.pearsonr(freight_df["avg_freight_ratio"], freight_df["pct_bad_review"])
    tests["Correlation: seller-state freight ratio vs. bad-review rate"] = {
        "stat": f"r={r:.4f}", "p": p, "n": len(freight_df)
    }

if not tests:
    st.warning("Not enough data in the current filter selection to run any test.")
    st.stop()

alpha = 0.05
verdicts = holm_bonferroni({k: v["p"] for k, v in tests.items()}, alpha=alpha)

rows = []
for name, t in tests.items():
    p_display = "<1e-300" if t["p"] == 0 else f"{t['p']:.4g}"
    rows.append({
        "Test": name, "Statistic": t["stat"], "n": t["n"], "p-value": p_display,
        f"Naive a={alpha}": "significant" if t["p"] <= alpha else "not sig.",
        "Holm-Bonferroni": "significant" if verdicts[name] else "not sig.",
    })
results_df = pd.DataFrame(rows)
st.dataframe(results_df, use_container_width=True, hide_index=True)

st.caption(
    f"Family of {len(tests)} tests under the current filter selection, Holm-Bonferroni family-wise alpha = {alpha}. "
    "Narrowing the filters changes sample sizes and can flip a verdict -- that's expected, not a bug: "
    "smaller filtered samples have less power to detect the same effect."
)

st.info(
    "**So what:** the correction does real work on the unfiltered full dataset -- the payment-type "
    "repeat-rate comparison clears a naive p<0.05 but is correctly reclassified as noise once judged "
    "against the family-wise bar. That's the difference between recommending a payment-method "
    "investigation and correctly declining to.",
    icon="💡",
)
download_csv_button(results_df, "statistical_tests_results.csv")
