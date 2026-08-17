"""Golden-value regression tests for analysis/statistical_tests.py's five
significance tests, run against the real committed database/olist.db.

The dataset is fixed and committed, so these are legitimate exact-ish
targets (not flaky "any reasonable value" assertions) -- expected values were
captured by running `python3 analysis/statistical_tests.py` directly and are
also documented in the README's "Statistical rigor pass" section. A failure
here means either the underlying SQL changed behaviour or the dataset itself
changed -- both worth knowing about immediately, not discovering via a
silently different dashboard number.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
# Aliased on import (rather than `from statistical_tests import test_1_...`):
# a bare `test_`-prefixed name imported into this module's namespace gets
# picked up by pytest's own collector as an additional (fixture-less) test
# item, since pytest doesn't distinguish "defined here" from "imported here".
from statistical_tests import (
    holm_bonferroni,
)
from statistical_tests import (
    test_1_category_first_vs_repeat as run_test_1,
)
from statistical_tests import (
    test_2_delivery_late_vs_bad_review as run_test_2,
)
from statistical_tests import (
    test_3_payment_type_vs_repeat as run_test_3,
)
from statistical_tests import (
    test_4_delivery_days_vs_review_score as run_test_4,
)
from statistical_tests import (
    test_5_freight_ratio_vs_bad_review_by_state as run_test_5,
)


def test_1_category_mix_chi_square(db_conn):
    result = run_test_1(db_conn)
    assert result["statistic"] == "chi2=317.99, dof=15"
    assert result["p_value"] == pytest.approx(1.011e-58, rel=0.01)
    assert result["n"] == 112_650


def test_2_late_delivery_bad_review_z_test(db_conn):
    result = run_test_2(db_conn)
    assert result["statistic"] == "z=112.80"
    assert result["p_value"] == pytest.approx(0.0, abs=1e-100)
    assert result["n"] == 96_353
    assert "54.0%" in result["name"]
    assert "9.2%" in result["name"]


def test_3_payment_type_chi_square_naively_significant(db_conn):
    result = run_test_3(db_conn)
    assert result["statistic"] == "chi2=8.38, dof=3"
    assert result["p_value"] == pytest.approx(0.03878, rel=0.01)
    assert result["n"] == 96_093
    # naively significant at alpha=0.05 -- the Holm-corrected flip is
    # verified separately below, against the full family of 5.
    assert result["p_value"] <= 0.05


def test_4_delivery_days_vs_review_score_pearson(db_conn):
    result = run_test_4(db_conn)
    assert result["statistic"] == "r=-0.3338"
    assert result["p_value"] == pytest.approx(0.0, abs=1e-100)
    assert result["n"] == 96_353


def test_5_freight_ratio_vs_bad_review_pearson(db_conn):
    result = run_test_5(db_conn)
    assert result["statistic"] == "r=0.3462"
    assert result["p_value"] == pytest.approx(0.1734, rel=0.01)
    assert result["n"] == 17


class TestFullFamilyHolmCorrection:
    """End-to-end: run all 5 tests, apply Holm-Bonferroni, and confirm the
    exact naive-vs-corrected split documented in the README (4/5 naively
    significant, 3/5 after correction -- test 3 is the one that flips)."""

    @pytest.fixture(scope="class")
    def results(self, db_conn):
        return [
            run_test_1(db_conn),
            run_test_2(db_conn),
            run_test_3(db_conn),
            run_test_4(db_conn),
            run_test_5(db_conn),
        ]

    def test_naive_significant_count(self, results):
        n_naive_sig = sum(1 for t in results if t["p_value"] <= 0.05)
        assert n_naive_sig == 4

    def test_holm_significant_count_and_flip(self, results):
        verdicts = holm_bonferroni([(t["name"], t["p_value"]) for t in results], alpha=0.05)
        n_holm_sig = sum(1 for sig, _ in verdicts.values() if sig)
        assert n_holm_sig == 3

        payment_type_result = results[2]
        assert payment_type_result["p_value"] <= 0.05  # naively significant
        assert verdicts[payment_type_result["name"]][0] is False  # Holm: not significant
