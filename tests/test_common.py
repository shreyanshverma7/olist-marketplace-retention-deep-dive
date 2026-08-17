"""Pure-logic unit tests for streamlit_app/common.py -- no DB, no Streamlit
runtime needed. These are the cheapest, highest-value tests in the suite:
filtered_orders_cte and format_currency_compact are exercised on every single
page load, so a regression here breaks every dashboard page at once."""

import pytest
from common import Filters, filtered_orders_cte, format_currency_compact


class TestFormatCurrencyCompact:
    def test_none(self):
        assert format_currency_compact(None) == "R$ 0"

    def test_zero(self):
        assert format_currency_compact(0) == "R$ 0"

    def test_small_value_no_suffix(self):
        assert format_currency_compact(500) == "R$ 500"
        assert format_currency_compact(999) == "R$ 999"

    def test_k_threshold(self):
        assert format_currency_compact(1000) == "R$ 1.0K"
        assert format_currency_compact(420_500) == "R$ 420.5K"

    def test_m_threshold(self):
        assert format_currency_compact(1_000_000) == "R$ 1.00M"
        assert format_currency_compact(15_373_842) == "R$ 15.37M"

    def test_just_under_m_threshold_rounds_up_to_1000_0k(self):
        # Documents actual behaviour, not a fix: 999_999 / 1000 = 999.999,
        # which rounds to "1,000.0K" at .1f precision instead of crossing
        # into the M-scale branch (that branch is chosen by the raw value,
        # not the rounded display). A real, currently-shipped display quirk.
        assert format_currency_compact(999_999) == "R$ 1,000.0K"

    def test_negative_value(self):
        assert format_currency_compact(-1_500_000) == "R$ -1.50M"


class TestFiltersDataclass:
    def test_defaults_are_empty_lists(self):
        f = Filters(start_date="2017-01-01", end_date="2018-01-01")
        assert f.states == []
        assert f.categories == []
        assert f.payment_types == []

    def test_default_factory_instances_are_independent(self):
        # Classic mutable-default-factory footgun: two instances must not
        # share the same underlying list object.
        f1 = Filters(start_date="2017-01-01", end_date="2018-01-01")
        f2 = Filters(start_date="2017-01-01", end_date="2018-01-01")
        f1.states.append("SP")
        assert f2.states == []


class TestFilteredOrdersCte:
    def test_no_filters(self):
        filters = Filters(start_date="2017-01-01", end_date="2018-01-01")
        cte, params = filtered_orders_cte(filters)

        assert "SELECT o.order_id" in cte
        assert "SELECT DISTINCT o.order_id" not in cte
        assert "JOIN customers" not in cte
        assert "JOIN order_items" not in cte
        assert "JOIN order_payments" not in cte
        assert "MATERIALIZED" in cte
        assert params == ("2017-01-01", "2018-01-01 23:59:59")

    def test_states_only_does_not_trigger_distinct(self):
        filters = Filters(start_date="2017-01-01", end_date="2018-01-01", states=["SP", "RJ"])
        cte, params = filtered_orders_cte(filters)

        assert "JOIN customers c ON o.customer_id = c.customer_id" in cte
        assert "c.customer_state IN (?,?)" in cte
        assert "SELECT DISTINCT o.order_id" not in cte
        assert params == ("2017-01-01", "2018-01-01 23:59:59", "SP", "RJ")

    def test_categories_only_triggers_distinct(self):
        filters = Filters(start_date="2017-01-01", end_date="2018-01-01", categories=["toys"])
        cte, params = filtered_orders_cte(filters)

        assert "JOIN order_items oi_f ON oi_f.order_id = o.order_id" in cte
        assert "JOIN products p_f ON p_f.product_id = oi_f.product_id" in cte
        assert "LEFT JOIN category_translation t_f" in cte
        assert "SELECT DISTINCT o.order_id" in cte
        assert params == ("2017-01-01", "2018-01-01 23:59:59", "toys")

    def test_payment_types_only_triggers_distinct(self):
        filters = Filters(start_date="2017-01-01", end_date="2018-01-01", payment_types=["credit_card"])
        cte, params = filtered_orders_cte(filters)

        assert "JOIN order_payments pay_f ON pay_f.order_id = o.order_id" in cte
        assert "pay_f.payment_type IN (?)" in cte
        assert "SELECT DISTINCT o.order_id" in cte
        assert params == ("2017-01-01", "2018-01-01 23:59:59", "credit_card")

    def test_all_filters_combined(self):
        filters = Filters(
            start_date="2017-01-01", end_date="2018-01-01",
            states=["SP"], categories=["toys", "books"], payment_types=["credit_card"],
        )
        cte, params = filtered_orders_cte(filters)

        assert "JOIN customers" in cte
        assert "JOIN order_items oi_f" in cte
        assert "JOIN order_payments pay_f" in cte
        assert "SELECT DISTINCT o.order_id" in cte
        assert params == (
            "2017-01-01", "2018-01-01 23:59:59", "SP", "toys", "books", "credit_card",
        )

    @pytest.mark.parametrize("n_states", [1, 3, 5])
    def test_placeholder_count_matches_list_length(self, n_states):
        states = [f"S{i}" for i in range(n_states)]
        filters = Filters(start_date="2017-01-01", end_date="2018-01-01", states=states)
        cte, params = filtered_orders_cte(filters)

        assert f"IN ({','.join('?' * n_states)})" in cte
        assert params[2:] == tuple(states)
