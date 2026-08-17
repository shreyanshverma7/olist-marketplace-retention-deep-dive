"""Guards the app's single accent-color invariant. common.ORANGE is meant to
be the one source of truth for the app's primary accent (also mirrored in
.streamlit/config.toml's primaryColor) -- these tests catch it drifting out
of sync with the KPI-card CSS or the payment-type palette."""

from unittest.mock import patch

from common import ORANGE, PAYMENT_TYPE_COLORS, inject_custom_css


def test_orange_is_the_documented_hex():
    assert ORANGE == "#D97757"


def test_credit_card_uses_the_primary_accent():
    assert PAYMENT_TYPE_COLORS["credit_card"] == ORANGE


def test_payment_type_colors_are_all_distinct():
    # A duplicate color would make two payment types visually indistinguishable
    # in any chart that uses this palette.
    assert len(set(PAYMENT_TYPE_COLORS.values())) == len(PAYMENT_TYPE_COLORS)


def test_inject_custom_css_interpolates_orange():
    with patch("common.st.markdown") as mock_markdown:
        inject_custom_css()

    assert mock_markdown.call_count == 1
    css = mock_markdown.call_args.args[0]
    assert ORANGE in css
    assert mock_markdown.call_args.kwargs.get("unsafe_allow_html") is True
