"""Dashboard smoke tests using Streamlit's own official headless test API
(streamlit.testing.v1.AppTest) -- runs each page's script in-process, no
server, no browser, no port, and no Claude-in-Chrome extension involved.

This directly replaces the weak part of CI's existing curl-based smoke test:
curl only proves the server returned HTTP 200, which is exactly the class of
bug that let the KPI-truncation issue (fixed in PR #1/#2) ship unnoticed --
the page rendered *something*, just not the right thing. AppTest surfaces the
actual Python exception if a page's script raises, and lets us assert on
what was actually rendered (KPI values, sidebar widgets), not just that a
response came back.
"""

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent / "streamlit_app"

PAGE_FILES = [
    "app.py",
    "pages/1_Cohort_Retention.py",
    "pages/2_Repeat_Purchase.py",
    "pages/3_Category_Drilldown.py",
    "pages/4_Delivery_vs_Reviews.py",
    "pages/5_Revenue_Concentration.py",
    "pages/6_Payments_and_Installments.py",
    "pages/7_Logistics_Freight.py",
    "pages/8_Statistical_Tests.py",
    "pages/9_Order_Status_Funnel.py",
    "pages/10_Customer_Segments_RFM.py",
]


@pytest.mark.parametrize("page_file", PAGE_FILES)
def test_page_runs_without_exception(page_file):
    at = AppTest.from_file(str(STREAMLIT_APP_DIR / page_file))
    at.run(timeout=30)
    assert not at.exception, f"{page_file} raised: {at.exception}"


class TestHomePageContent:
    @pytest.fixture(scope="class")
    def at(self):
        app = AppTest.from_file(str(STREAMLIT_APP_DIR / "app.py"))
        app.run(timeout=30)
        return app

    def test_no_exception(self, at):
        assert not at.exception

    def test_has_five_kpi_cards(self, at):
        assert len(at.metric) == 5

    def test_gmv_kpi_is_compact_formatted_not_truncated(self, at):
        gmv_metrics = [m for m in at.metric if "GMV" in m.label]
        assert len(gmv_metrics) == 1
        # e.g. "R$ 15.37M" -- guards against the original truncation bug
        # ("R$ 15,373,...") ever regressing.
        assert re.fullmatch(r"R\$ [\d,]+(\.\d+)?[KM]?", gmv_metrics[0].value), gmv_metrics[0].value

    def test_reset_filters_button_present(self, at):
        labels = [b.label for b in at.sidebar.button]
        assert "Reset filters" in labels

    def test_date_preset_buttons_present(self, at):
        labels = [b.label for b in at.sidebar.button]
        assert {"3mo", "6mo", "Full"}.issubset(set(labels))
