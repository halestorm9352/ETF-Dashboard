import unittest

from config import INVALID_TICKERS
from sec_filings import (
    _is_placeholder_share_class_name,
    _merge_series_entries_with_pairs,
)
from sec_parsers import (
    extract_named_ticker_pairs,
    extract_series_entries,
    sanitize_ticker,
)
from theme_classifier import (
    LEVERAGED_THEME,
    OPTIONS_INCOME_THEME,
    TARGET_MATURITY_THEME,
    classify_primary_theme,
)


class TickerHygieneTests(unittest.TestCase):
    def test_structured_ticker_sanitizer_accepts_two_to_five_letters(self):
        self.assertEqual(sanitize_ticker("AB"), "AB")
        self.assertEqual(sanitize_ticker("ABCDE"), "ABCDE")

    def test_five_letter_series_table_ticker_survives(self):
        entries = extract_series_entries(
            """
            <table>
              <tr><td class="seriesName">Series S000000001</td>
                  <td class="seriesCell">new</td>
                  <td class="seriesCell">Example ETF</td></tr>
              <tr class="contractRow">
                  <td>Class/Contract C000000001</td><td></td>
                  <td>Example ETF</td><td>ABCDE</td></tr>
            </table>
            """
        )

        self.assertEqual(entries[0]["ticker"], "ABCDE")

    def test_exchange_and_false_positive_terms_are_invalid_tickers(self):
        for ticker in ("CBOE", "EDGX", "ARCA", "BATS", "LONG"):
            with self.subTest(ticker=ticker):
                self.assertIn(ticker, INVALID_TICKERS)
                self.assertEqual(sanitize_ticker(ticker), "Not Listed")

    def test_trex_name_does_not_receive_cboe_as_ticker(self):
        pairs = extract_named_ticker_pairs(
            """
            <table><tr>
              <td>T-REX 2X LONG HIVE DAILY TARGET ETF</td><td>CBOE</td>
            </tr></table>
            """
        )

        self.assertEqual(pairs, [])

    def test_ambiguous_candidate_ticker_is_not_assigned_to_multiple_series(self):
        entries = [
            {"etf_name": "Direxion PYPL ETF", "ticker": ""},
            {"etf_name": "Direxion PYPL ETF Daily Shares", "ticker": ""},
        ]
        pairs = [{"etf_name": "Direxion PYPL ETF", "ticker": "PYPL"}]

        merged = _merge_series_entries_with_pairs(entries, pairs)

        self.assertEqual([entry["ticker"] for entry in merged], ["", ""])

    def test_single_fund_candidate_ticker_is_still_assigned(self):
        entries = [{"etf_name": "Direxion PYPL ETF", "ticker": ""}]
        pairs = [{"etf_name": "Direxion PYPL ETF", "ticker": "PYPL"}]

        merged = _merge_series_entries_with_pairs(entries, pairs)

        self.assertEqual(merged[0]["ticker"], "PYPL")


class PlaceholderShareClassTests(unittest.TestCase):
    def test_class_only_names_are_placeholders(self):
        names = (
            "Institutional Class",
            "Class 529-A",
            "Class C Shares",
            "Investor Class Shares",
            "Retail Class",
            "Example Fund: Class X",
        )

        for name in names:
            with self.subTest(name=name):
                self.assertTrue(_is_placeholder_share_class_name(name))

    def test_mutual_fund_name_is_not_a_placeholder(self):
        self.assertFalse(_is_placeholder_share_class_name("Fidelity Contrafund"))


class ThemeHygieneTests(unittest.TestCase):
    def test_option_income_name_is_options_income(self):
        self.assertEqual(
            classify_primary_theme("YieldMax PLTR Option Income Strategy ETF"),
            OPTIONS_INCOME_THEME,
        )

    def test_short_term_treasury_is_not_leveraged(self):
        self.assertNotEqual(
            classify_primary_theme("Schwab Short-Term U.S. Treasury ETF"),
            LEVERAGED_THEME,
        )

    def test_quadpro_name_is_leveraged(self):
        self.assertEqual(
            classify_primary_theme("ProShares QuadPro Russell2000"),
            LEVERAGED_THEME,
        )

    def test_ladder_and_ibonds_names_are_target_maturity(self):
        for name in ("Corporate Bond Ladder ETF", "iBonds Treasury ETF"):
            with self.subTest(name=name):
                self.assertEqual(classify_primary_theme(name), TARGET_MATURITY_THEME)


if __name__ == "__main__":
    unittest.main()
