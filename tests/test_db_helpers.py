"""Structural tests for common.py's thin DB-access wrappers, run against the
real committed database. Verified experimentally that @st.cache_data /
@st.cache_resource degrade to harmless no-ops (with stderr warnings) outside
a real Streamlit runtime rather than raising, which is what makes calling
these directly from pytest viable."""

import pandas as pd
from common import _filter_options, get_connection, run_query


def test_get_connection_returns_working_sqlite_connection():
    conn = get_connection()
    cur = conn.execute("SELECT COUNT(*) FROM orders")
    assert cur.fetchone()[0] == 99_441


def test_run_query_returns_dataframe():
    df = run_query("SELECT COUNT(*) AS n FROM orders")
    assert isinstance(df, pd.DataFrame)
    assert df["n"].iloc[0] == 99_441


def test_run_query_respects_params():
    df = run_query(
        "SELECT COUNT(*) AS n FROM orders WHERE order_status = ?", ("delivered",)
    )
    assert df["n"].iloc[0] > 0
    assert df["n"].iloc[0] < 99_441  # not every order is delivered


class TestFilterOptions:
    def test_returns_five_values(self):
        result = _filter_options()
        assert len(result) == 5

    def test_states_non_empty_and_sorted(self):
        states, *_ = _filter_options()
        assert len(states) > 0
        assert states == sorted(states)

    def test_categories_non_empty(self):
        _, categories, *_ = _filter_options()
        assert len(categories) > 0
        assert None not in categories

    def test_payment_types_excludes_not_defined(self):
        _, _, payment_types, _, _ = _filter_options()
        assert "not_defined" not in payment_types
        assert len(payment_types) > 0

    def test_date_bounds_are_valid_iso_dates(self):
        *_, lo, hi = _filter_options()
        # sliced to [:10] in common.py -- expect a bare "YYYY-MM-DD"
        assert len(lo) == 10
        assert len(hi) == 10
        assert lo <= hi
