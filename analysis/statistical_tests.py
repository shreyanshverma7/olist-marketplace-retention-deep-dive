"""Statistical rigor pass for the Olist retention/behaviour analysis.

Runs every rate/segment comparison surfaced by sql/*.sql through a formal
significance test, then applies Holm-Bonferroni correction across the full
family of five tests (they are not independent research questions -- they're
all comparisons drawn from the same project, so the family-wise error rate
needs controlling the same way Project 1's did).

Usage: python3 analysis/statistical_tests.py
"""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "olist.db"


def two_proportion_z_test(x1, n1, x2, n2):
    """Two-proportion z-test. Returns (z, p_two_sided)."""
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return z, p, p1, p2


def holm_bonferroni(results, alpha=0.05):
    """Holm's step-down procedure. results: list of (name, p_value)."""
    m = len(results)
    ordered = sorted(results, key=lambda r: r[1])
    verdicts = {}
    reject_all_remaining = False
    for i, (name, p) in enumerate(ordered):
        threshold = alpha / (m - i)
        if not reject_all_remaining and p <= threshold:
            verdicts[name] = (True, threshold)
        else:
            reject_all_remaining = True  # once one fails, all later (larger p) fail too
            verdicts[name] = (False, threshold)
    return verdicts


def test_1_category_first_vs_repeat(conn):
    """Chi-square test of independence: category distribution, first vs repeat purchase."""
    query = """
        WITH customer_orders AS (
            SELECT c.customer_unique_id, o.order_id,
                   ROW_NUMBER() OVER (PARTITION BY c.customer_unique_id ORDER BY o.order_purchase_timestamp) AS order_seq
            FROM orders o JOIN customers c ON o.customer_id = c.customer_id
        ),
        items_with_category AS (
            SELECT co.order_seq,
                   COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category
            FROM customer_orders co
            JOIN order_items oi ON oi.order_id = co.order_id
            JOIN products p ON p.product_id = oi.product_id
            LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
        ),
        top_categories AS (
            SELECT category FROM items_with_category GROUP BY category
            ORDER BY COUNT(*) DESC LIMIT 15
        )
        SELECT
            CASE WHEN category IN (SELECT category FROM top_categories) THEN category ELSE 'other' END AS category,
            CASE WHEN order_seq = 1 THEN 'first' ELSE 'repeat' END AS purchase_type,
            COUNT(*) AS n
        FROM items_with_category
        GROUP BY 1, 2
    """
    df = pd.read_sql(query, conn)
    table = df.pivot(index="category", columns="purchase_type", values="n").fillna(0)
    chi2, p, dof, _ = stats.chi2_contingency(table)
    return {
        "name": "Category mix: first vs. repeat purchase items (chi-square, 16 categories)",
        "statistic": f"chi2={chi2:.2f}, dof={dof}",
        "p_value": p,
        "n": int(table.values.sum()),
    }


def test_2_delivery_late_vs_bad_review(conn):
    """Two-proportion z-test: bad-review rate, on-time vs. late delivery."""
    query = """
        SELECT
            CASE WHEN o.order_delivered_customer_date <= o.order_estimated_delivery_date
                 THEN 'on_time' ELSE 'late' END AS flag,
            SUM(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) AS bad,
            COUNT(*) AS n
        FROM orders o JOIN order_reviews r ON r.order_id = o.order_id
        WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
        GROUP BY flag
    """
    df = pd.read_sql(query, conn).set_index("flag")
    z, p, p_late, p_ontime = two_proportion_z_test(
        df.loc["late", "bad"], df.loc["late", "n"],
        df.loc["on_time", "bad"], df.loc["on_time", "n"],
    )
    return {
        "name": f"Bad-review rate: late ({p_late:.1%}) vs. on-time ({p_ontime:.1%}) delivery (two-proportion z)",
        "statistic": f"z={z:.2f}",
        "p_value": p,
        "n": int(df["n"].sum()),
    }


def test_3_payment_type_vs_repeat(conn):
    """Chi-square test of independence: payment type (first order) vs. repeat-customer status."""
    query = """
        WITH ranked_payments AS (
            SELECT order_id, payment_type, payment_value,
                   ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY payment_value DESC) AS rnk
            FROM order_payments
        ),
        order_payment_agg AS (
            SELECT order_id, MAX(CASE WHEN rnk = 1 THEN payment_type END) AS primary_payment_type
            FROM ranked_payments GROUP BY order_id
        ),
        customer_orders AS (
            SELECT c.customer_unique_id, o.order_id,
                   ROW_NUMBER() OVER (PARTITION BY c.customer_unique_id ORDER BY o.order_purchase_timestamp) AS order_seq
            FROM orders o JOIN customers c ON o.customer_id = c.customer_id
        ),
        per_customer AS (
            SELECT customer_unique_id, MAX(order_seq) AS total_orders FROM customer_orders GROUP BY customer_unique_id
        ),
        first_order_payment AS (
            SELECT co.customer_unique_id, opa.primary_payment_type
            FROM customer_orders co JOIN order_payment_agg opa ON opa.order_id = co.order_id
            WHERE co.order_seq = 1 AND opa.primary_payment_type IN ('credit_card','boleto','voucher','debit_card')
        )
        SELECT fop.primary_payment_type AS payment_type,
               CASE WHEN pc.total_orders >= 2 THEN 'repeat' ELSE 'one_time' END AS status,
               COUNT(*) AS n
        FROM first_order_payment fop JOIN per_customer pc ON pc.customer_unique_id = fop.customer_unique_id
        GROUP BY 1, 2
    """
    df = pd.read_sql(query, conn)
    table = df.pivot(index="payment_type", columns="status", values="n").fillna(0)
    chi2, p, dof, _ = stats.chi2_contingency(table)
    return {
        "name": "Repeat-customer rate by first-order payment type (chi-square, 4 types)",
        "statistic": f"chi2={chi2:.2f}, dof={dof}",
        "p_value": p,
        "n": int(table.values.sum()),
    }


def test_4_delivery_days_vs_review_score(conn):
    """Pearson correlation: delivery days vs. review score, order-level."""
    query = """
        SELECT julianday(o.order_delivered_customer_date) - julianday(o.order_purchase_timestamp) AS delivery_days,
               r.review_score
        FROM orders o JOIN order_reviews r ON r.order_id = o.order_id
        WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
    """
    df = pd.read_sql(query, conn)
    r, p = stats.pearsonr(df["delivery_days"], df["review_score"])
    return {
        "name": "Correlation: delivery days vs. review score (Pearson, order-level)",
        "statistic": f"r={r:.4f}",
        "p_value": p,
        "n": len(df),
    }


def test_5_freight_ratio_vs_bad_review_by_state(conn):
    """Pearson correlation: state-level avg freight ratio vs. state-level bad-review rate.

    Ecological (state-aggregated) correlation, n=17 states -- flagged separately
    in the writeup as a much weaker design than the order-level test above.
    """
    query = """
        WITH item_freight AS (
            SELECT s.seller_state, oi.freight_value / oi.price AS freight_ratio, r.review_score
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.order_id
            JOIN sellers s ON s.seller_id = oi.seller_id
            JOIN order_reviews r ON r.order_id = o.order_id
            WHERE o.order_status = 'delivered' AND oi.price > 0
        )
        SELECT seller_state,
               AVG(freight_ratio) AS avg_freight_ratio,
               100.0 * SUM(CASE WHEN review_score <= 2 THEN 1 ELSE 0 END) / COUNT(*) AS pct_bad_review,
               COUNT(*) AS n
        FROM item_freight GROUP BY seller_state HAVING COUNT(*) >= 30
    """
    df = pd.read_sql(query, conn)
    r, p = stats.pearsonr(df["avg_freight_ratio"], df["pct_bad_review"])
    return {
        "name": "Correlation: seller-state freight ratio vs. bad-review rate (Pearson, state-level, n=17 states)",
        "statistic": f"r={r:.4f}",
        "p_value": p,
        "n": len(df),
    }


def main():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    tests = [
        test_1_category_first_vs_repeat(conn),
        test_2_delivery_late_vs_bad_review(conn),
        test_3_payment_type_vs_repeat(conn),
        test_4_delivery_days_vs_review_score(conn),
        test_5_freight_ratio_vs_bad_review_by_state(conn),
    ]
    conn.close()

    alpha = 0.05
    verdicts = holm_bonferroni([(t["name"], t["p_value"]) for t in tests], alpha=alpha)

    print(f"Statistical rigor pass -- {len(tests)} tests, Holm-Bonferroni family-wise alpha = {alpha}\n")
    print(f"{'#':<3}{'Test':<70}{'p-value':<12}{'naive a=.05':<14}{'Holm verdict':<14}")
    print("-" * 113)
    for i, t in enumerate(tests, 1):
        naive = "significant" if t["p_value"] <= alpha else "not sig."
        holm_sig, threshold = verdicts[t["name"]]
        holm = "significant" if holm_sig else "not sig."
        # exact 0.0 is float underflow, not a true zero probability -- report a bound instead
        p_display = "<1e-300" if t["p_value"] == 0 else f"{t['p_value']:.4g}"
        print(f"{i:<3}{t['name'][:68]:<70}{p_display:<12}{naive:<14}{holm:<14}")
        print(f"    {t['statistic']}, n={t['n']:,}, Holm threshold at this rank={threshold:.4g}")
    print()

    n_naive_sig = sum(1 for t in tests if t["p_value"] <= alpha)
    n_holm_sig = sum(1 for sig, _ in verdicts.values() if sig)
    print(f"Naive alpha=0.05: {n_naive_sig}/{len(tests)} tests significant.")
    print(f"Holm-Bonferroni:  {n_holm_sig}/{len(tests)} tests significant.")
    if n_naive_sig > n_holm_sig:
        print("The correction reclassified at least one naively-significant result as noise --")
        print("that's the point of running it on a family of 5 tests instead of judging each alone.")


if __name__ == "__main__":
    main()
