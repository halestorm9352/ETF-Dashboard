import unittest

from sec_filings import (
    _enrich_missing_tickers_from_later_filings,
    derive_latest_fund_rows,
)
from sec_parsers import extract_rule_485_effectiveness


class Rule485EffectivenessTests(unittest.TestCase):
    def test_detects_checked_75_day_option(self):
        html = """
        <table>
          <tr><td>&#9744;</td><td>60 days after filing pursuant to paragraph (a)(1)</td></tr>
          <tr><td>X</td><td>75 days after filing pursuant to paragraph (a)(2)</td></tr>
        </table>
        """

        result = extract_rule_485_effectiveness(html)

        self.assertEqual(result["effectiveness_basis"], "rule_485_a2_75_days")
        self.assertEqual(result["effectiveness_days"], 75)

    def test_detects_checked_60_day_option(self):
        html = """
        <table>
          <tr><td>[X]</td><td>60 days after filing pursuant to paragraph (a)(1)</td></tr>
          <tr><td>[ ]</td><td>75 days after filing pursuant to paragraph (a)(2)</td></tr>
        </table>
        """

        result = extract_rule_485_effectiveness(html)

        self.assertEqual(result["effectiveness_basis"], "rule_485_a1_60_days")
        self.assertEqual(result["effectiveness_days"], 60)

    def test_detects_immediate_rule_485_b_option(self):
        html = """
        <table>
          <tr><td><input type="checkbox" checked></td>
              <td>immediately upon filing pursuant to paragraph (b)</td></tr>
        </table>
        """

        result = extract_rule_485_effectiveness(html)

        self.assertEqual(result["effectiveness_basis"], "rule_485_b_immediate")
        self.assertEqual(result["effectiveness_days"], 0)

    def test_detects_designated_effective_date(self):
        html = """
        <table>
          <tr><td>X</td><td>on June 11, 2026 pursuant to paragraph (b)</td></tr>
        </table>
        """

        result = extract_rule_485_effectiveness(html)

        self.assertEqual(result["effectiveness_basis"], "rule_485_b_designated_date")
        self.assertEqual(result["designated_effective_date"], "June 11, 2026")

    def test_ignores_unchecked_options(self):
        html = """
        <table>
          <tr><td>&#9744;</td><td>60 days after filing pursuant to paragraph (a)(1)</td></tr>
          <tr><td>&#9744;</td><td>75 days after filing pursuant to paragraph (a)(2)</td></tr>
        </table>
        """

        result = extract_rule_485_effectiveness(html)

        self.assertEqual(result["effectiveness_basis"], "")
        self.assertIsNone(result["effectiveness_days"])


class FilingHistoryTests(unittest.TestCase):
    def test_latest_snapshot_does_not_remove_events_from_source_list(self):
        events = [
            {
                "cik": "0000000001",
                "etf_name": "Example ETF",
                "ticker": "EXAM",
                "date": "2026-06-10",
                "accepted_at": "2026-06-10T12:00:00Z",
            },
            {
                "cik": "0000000001",
                "etf_name": "Example ETF",
                "ticker": "Not Listed",
                "date": "2026-05-01",
                "accepted_at": "2026-05-01T12:00:00Z",
            },
        ]

        snapshot = derive_latest_fund_rows(events)

        self.assertEqual(len(events), 2)
        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot[0]["date"], "2026-06-10")

    def test_later_ticker_enrichment_preserves_ticker_at_filing(self):
        events = [
            {
                "cik": "0000000001",
                "etf_name": "Example ETF",
                "ticker": "EXAM",
                "ticker_at_filing": "EXAM",
                "date": "2026-06-10",
                "accepted_at": "2026-06-10T12:00:00Z",
            },
            {
                "cik": "0000000001",
                "etf_name": "Example ETF",
                "ticker": "Not Listed",
                "ticker_at_filing": "Not Listed",
                "date": "2026-05-01",
                "accepted_at": "2026-05-01T12:00:00Z",
            },
        ]

        enriched = _enrich_missing_tickers_from_later_filings(events)
        older_event = next(row for row in enriched if row["date"] == "2026-05-01")

        self.assertEqual(older_event["ticker"], "EXAM")
        self.assertEqual(older_event["ticker_at_filing"], "Not Listed")


if __name__ == "__main__":
    unittest.main()
