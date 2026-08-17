"""Unit tests for the pure math/algorithm helpers shared by
analysis/statistical_tests.py and streamlit_app/pages/8_Statistical_Tests.py.

The two files each define their own copy of two_proportion_z_test and
holm_bonferroni (analysis/statistical_tests.py:22-45,
pages/8_Statistical_Tests.py:29-48) -- same logic, independently maintained.
Every case here runs against both copies so the two can't silently drift
apart; the page's holm_bonferroni takes a dict and returns bool per name
(no threshold), while the CLI script's takes a list of tuples and returns
(bool, threshold) per name -- tests account for that shape difference.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
from statistical_tests import (
    holm_bonferroni as cli_holm_bonferroni,
)
from statistical_tests import (
    two_proportion_z_test as cli_two_proportion_z_test,
)


class TestTwoProportionZTestCli:
    def test_identical_proportions_gives_z_zero_p_one(self):
        z, p, p1, p2 = cli_two_proportion_z_test(50, 100, 50, 100)
        assert z == pytest.approx(0.0, abs=1e-9)
        assert p == pytest.approx(1.0, abs=1e-9)
        assert p1 == p2 == 0.5

    def test_clearly_different_proportions(self):
        # Matches the shape of the real late-vs-on-time comparison: a large,
        # obviously-significant gap should produce a tiny p-value.
        z, p, p1, p2 = cli_two_proportion_z_test(540, 1000, 92, 1000)
        assert z > 20
        assert p < 1e-10
        assert p1 == pytest.approx(0.54)
        assert p2 == pytest.approx(0.092)

    def test_symmetric_in_argument_order(self):
        z1, p1, _, _ = cli_two_proportion_z_test(30, 200, 60, 200)
        z2, p2, _, _ = cli_two_proportion_z_test(60, 200, 30, 200)
        assert z1 == pytest.approx(-z2)
        assert p1 == pytest.approx(p2)


class TestPageTwoProportionZTestMatchesCli:
    def test_matches_cli_implementation(self, page8):
        z_cli, p_cli, _, _ = cli_two_proportion_z_test(540, 1000, 92, 1000)
        z_page, p_page = page8.two_proportion_z_test(540, 1000, 92, 1000)
        assert z_page == pytest.approx(z_cli)
        assert p_page == pytest.approx(p_cli)


class TestHolmBonferroniCli:
    def test_all_tiny_pvalues_all_significant(self):
        results = [("a", 1e-10), ("b", 1e-9), ("c", 1e-8)]
        verdicts = cli_holm_bonferroni(results, alpha=0.05)
        assert all(sig for sig, _ in verdicts.values())

    def test_step_down_blocks_everything_after_first_failure(self):
        # Reproduces the documented real-world flip: 4 very significant
        # results plus one borderline one (p~0.039) that clears the naive
        # alpha=0.05 bar but fails once ranked into the family of 5.
        results = [
            ("t1", 1.0e-58), ("t2", 1e-300), ("t3", 0.03878),
            ("t4", 1e-300), ("t5", 0.1734),
        ]
        verdicts = cli_holm_bonferroni(results, alpha=0.05)
        assert verdicts["t1"][0] is True
        assert verdicts["t2"][0] is True
        assert verdicts["t3"][0] is False  # the documented flip
        assert verdicts["t4"][0] is True
        assert verdicts["t5"][0] is False

    def test_threshold_formula(self):
        # threshold at rank i (0-indexed) = alpha / (m - i)
        results = [("a", 0.5), ("b", 0.4), ("c", 0.3)]
        verdicts = cli_holm_bonferroni(results, alpha=0.06)
        # sorted ascending: c(0.3), b(0.4), a(0.5) -> ranks 0,1,2 -> m=3
        assert verdicts["c"][1] == pytest.approx(0.06 / 3)
        assert verdicts["b"][1] == pytest.approx(0.06 / 2)
        assert verdicts["a"][1] == pytest.approx(0.06 / 1)


class TestPageHolmBonferroniMatchesCli:
    def test_same_verdicts_as_cli_for_the_documented_flip(self, page8):
        pvals = {"t1": 1.0e-58, "t2": 1e-300, "t3": 0.03878, "t4": 1e-300, "t5": 0.1734}
        cli_verdicts = cli_holm_bonferroni(list(pvals.items()), alpha=0.05)
        page_verdicts = page8.holm_bonferroni(pvals, alpha=0.05)

        for name in pvals:
            assert page_verdicts[name] == cli_verdicts[name][0]
