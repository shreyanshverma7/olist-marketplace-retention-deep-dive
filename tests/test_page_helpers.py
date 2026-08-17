"""Tests for the pure-Python helper functions defined inside
streamlit_app/pages/5_Revenue_Concentration.py -- loaded via the `page5`
fixture (importlib, since a numeric-prefixed filename like
"5_Revenue_Concentration.py" isn't a valid dotted import path)."""

import pandas as pd
import pytest


class TestTopNPct:
    @pytest.fixture
    def curve_df(self):
        # A small hand-built Lorenz-curve-shaped DataFrame: 10 entities,
        # ranked by revenue, cumulative % revenue increasing with rank.
        return pd.DataFrame({
            "rnk": list(range(1, 11)),
            "total_n": [10] * 10,
            "cum_pct_revenue": [40, 55, 65, 72, 78, 83, 87, 91, 96, 100],
        })

    def test_exact_breakpoint(self, page5, curve_df):
        # pct=20 of 10 entities -> target_rnk = round(0.2*10) = 2
        assert page5.top_n_pct(curve_df, 20) == 55

    def test_clamped_to_at_least_rank_1(self, page5, curve_df):
        # pct=0 -> round(0) = 0, clamped up to rnk=1
        assert page5.top_n_pct(curve_df, 0) == 40

    def test_clamped_to_at_most_total_n(self, page5, curve_df):
        # pct=100 -> round(10) = 10 = total_n, no clamping needed but exercises the upper bound
        assert page5.top_n_pct(curve_df, 100) == 100

    def test_pct_above_100_clamps_to_last_rank(self, page5, curve_df):
        assert page5.top_n_pct(curve_df, 150) == 100

    def test_rounds_to_nearest_rank(self, page5, curve_df):
        # pct=5 of 10 -> round(0.5) -> Python banker's rounding gives round(0.5)=0,
        # clamped to rnk=1 -- documents actual behaviour of the shared round().
        assert page5.top_n_pct(curve_df, 5) == 40


class TestLorenzQuery:
    def test_returns_a_string_containing_the_entity_col(self, page5):
        sql = page5.lorenz_query("c.customer_unique_id", "JOIN customers c ON c.customer_id = o.customer_id")
        assert isinstance(sql, str)
        assert "c.customer_unique_id" in sql
        assert "JOIN customers c ON c.customer_id = o.customer_id" in sql

    def test_output_has_expected_columns_and_rows(self, page5, db_conn):
        sql = page5.lorenz_query("oi.seller_id", "")
        # lorenz_query embeds a `{cte}` with unfilled "?" placeholders; page5's
        # own module-level `params` (from filtered_orders_cte(filters), set at
        # import time) are what the real page binds at query time -- reuse
        # them here to run the exact same query against the real DB.
        cur = db_conn.execute(sql, page5.params)
        cols = [d[0] for d in cur.description]
        assert cols == ["rnk", "total_n", "cum_pct_population", "cum_pct_revenue"]
        rows = cur.fetchall()
        assert len(rows) > 0

    def test_downsampled_output_always_includes_first_and_last_rank(self, page5, db_conn):
        sql = page5.lorenz_query("oi.seller_id", "")
        df = pd.read_sql_query(sql, db_conn, params=page5.params)
        assert df["rnk"].min() == 1
        assert df["rnk"].max() == df["total_n"].iloc[0]
