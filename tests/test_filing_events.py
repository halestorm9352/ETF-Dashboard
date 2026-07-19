import unittest
from datetime import date
import json
from unittest.mock import patch

from sec_filings import (
    _enrich_missing_tickers_from_later_filings,
    _enrich_tickers_from_sec_mapping,
    derive_latest_fund_rows,
    fetch_sec_fund_ticker_mapping,
    fetch_filing_events,
    normalize_event_ticker,
)
from sec_parsers import extract_rule_485_effectiveness
from vehicle_classifier import ETF_VEHICLE


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
    def test_sec_fund_ticker_mapping_uses_documented_field_order(self):
        payload = {
            "fields": ["cik", "seriesId", "classId", "symbol"],
            "data": [[1888997, "S000075036", "C000233738", "SELV"]],
        }

        with patch("sec_filings.get_response_text", return_value=json.dumps(payload)):
            mapping = fetch_sec_fund_ticker_mapping()

        self.assertEqual(
            mapping[("0001888997", "S000075036", "C000233738")],
            "SELV",
        )

    def test_exact_sec_identity_join_backfills_ticker_and_preserves_filing_value(self):
        event = {
            "cik": "0000819118",
            "series_id": "S000055364",
            "class_id": "C000174182",
            "etf_name": "Fidelity Large Cap Stock Fund",
            "ticker": "Not Listed",
            "ticker_at_filing": "Not Listed",
        }
        mapping = {
            ("0000819118", "S000055364", "C000174182"): "FLCSX",
            ("0000819118", "S000055364", "C000259429"): "FLAJX",
        }

        enriched = _enrich_tickers_from_sec_mapping([event], mapping)

        self.assertEqual(enriched[0]["ticker"], "FLCSX")
        self.assertEqual(enriched[0]["ticker_source"], "sec_fund_ticker_map")
        self.assertEqual(enriched[0]["ticker_at_filing"], "Not Listed")
        self.assertEqual(normalize_event_ticker(enriched[0]), "FLCSX")

    def test_fetch_pipeline_joins_parsed_ids_to_sec_mapping(self):
        index_text = """
        <table class="tableSeries">
          <tr><td class="seriesName">Series S000075036</td>
              <td class="seriesCell">new</td>
              <td class="seriesCell">SEI Large Cap Low Volatility Factor ETF</td></tr>
          <tr class="contractRow">
              <td>Class/Contract C000233738</td><td></td>
              <td>SEI Large Cap Low Volatility Factor ETF</td><td></td></tr>
        </table>
        """
        mapping_payload = {
            "fields": ["cik", "seriesId", "classId", "symbol"],
            "data": [[1888997, "S000075036", "C000233738", "SELV"]],
        }
        recent_filings = {
            "filer_name": "SEI Exchange Traded Funds",
            "recent": {
                "form": ["N-1A"],
                "filingDate": ["2026-01-15"],
                "acceptanceDateTime": ["2026-01-15T12:00:00Z"],
                "accessionNumber": ["0001104659-26-000001"],
                "primaryDocument": [""],
            },
        }

        def response_text(url, _max_chars):
            if url.endswith("company_tickers_mf.json"):
                return json.dumps(mapping_payload)
            return index_text

        with patch(
            "sec_filings.fetch_recent_filings_for_cik",
            return_value=recent_filings,
        ), patch("sec_filings.get_response_text", side_effect=response_text):
            events = fetch_filing_events(
                date(2026, 1, 1),
                date(2026, 1, 31),
                ciks=["0001888997"],
            )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["series_id"], "S000075036")
        self.assertEqual(events[0]["class_id"], "C000233738")
        self.assertEqual(events[0]["ticker"], "SELV")
        self.assertEqual(events[0]["ticker_at_filing"], "Not Listed")
        self.assertEqual(events[0]["vehicle"], ETF_VEHICLE)

    def test_later_filing_fallback_skips_rows_with_sec_identity(self):
        events = [
            {
                "cik": "0000000001",
                "series_id": "S000000001",
                "class_id": "C000000001",
                "etf_name": "Example ETF",
                "ticker": "EXAM",
                "date": "2026-06-10",
            },
            {
                "cik": "0000000001",
                "series_id": "S000000001",
                "class_id": "C000000001",
                "etf_name": "Example ETF",
                "ticker": "Not Listed",
                "date": "2026-05-01",
            },
        ]

        enriched = _enrich_missing_tickers_from_later_filings(events)

        self.assertEqual(enriched[1]["ticker"], "Not Listed")

    def test_snapshot_uses_ids_when_fund_name_changes(self):
        events = [
            {
                "cik": "0000000001",
                "series_id": "S000000001",
                "class_id": "C000000001",
                "etf_name": "Original Example ETF",
                "form": "N-1A",
                "date": "2026-01-10",
            },
            {
                "cik": "0000000001",
                "series_id": "S000000001",
                "class_id": "C000000001",
                "etf_name": "Renamed Example ETF",
                "form": "485BPOS",
                "date": "2026-04-10",
            },
        ]

        snapshot = derive_latest_fund_rows(events)

        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot[0]["etf_name"], "Renamed Example ETF")
        self.assertEqual(snapshot[0]["filing_event_count"], 2)

    def test_snapshot_bridges_name_only_history_to_unique_sec_identity(self):
        events = [
            {
                "cik": "0000000001",
                "etf_name": "Example ETF",
                "form": "N-1A",
                "date": "2026-01-10",
            },
            {
                "cik": "0000000001",
                "series_id": "S000000001",
                "class_id": "C000000001",
                "etf_name": "Example ETF",
                "form": "485BPOS",
                "date": "2026-04-10",
            },
        ]

        snapshot = derive_latest_fund_rows(events)

        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot[0]["filing_event_count"], 2)

    def test_two_cik_search_retains_healthy_events_and_reports_failure(self):
        healthy_cik = "0000000001"
        failed_cik = "0000000002"
        healthy_filings = {
            "filer_name": "Healthy Trust",
            "recent": {
                "form": ["N-1A"],
                "filingDate": ["2025-01-15"],
                "acceptanceDateTime": ["2025-01-15T12:00:00Z"],
                "accessionNumber": ["0000000001-25-000001"],
                "primaryDocument": [""],
            },
        }

        def fake_recent_filings(cik):
            if cik == failed_cik:
                raise RuntimeError("SEC submissions unavailable")
            return healthy_filings

        with patch(
            "sec_filings.fetch_recent_filings_for_cik",
            side_effect=fake_recent_filings,
        ), patch(
            "sec_filings.get_response_text",
            return_value="""
            <table><tr class="contractRow">
              <td></td><td></td><td>Healthy ETF</td><td>HLTH</td>
            </tr></table>
            """,
        ):
            events = fetch_filing_events(
                date(2025, 1, 1),
                date(2025, 1, 31),
                ciks=[healthy_cik, failed_cik],
            )

        statuses = {status["cik"]: status for status in events.statuses}
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["cik"], healthy_cik)
        self.assertTrue(statuses[healthy_cik]["success"])
        self.assertFalse(statuses[failed_cik]["success"])
        self.assertIn(
            "SEC submissions unavailable",
            statuses[failed_cik]["error_summary"],
        )

    def test_historical_search_does_not_fetch_beyond_enrichment_window(self):
        requested_urls = []
        recent_filings = {
            "filer_name": "Example Trust",
            "recent": {
                "form": ["N-1A", "N-1A", "N-1A"],
                "filingDate": ["2025-01-15", "2025-03-15", "2025-05-02"],
                "acceptanceDateTime": [
                    "2025-01-15T12:00:00Z",
                    "2025-03-15T12:00:00Z",
                    "2025-05-02T12:00:00Z",
                ],
                "accessionNumber": [
                    "0000000001-25-000001",
                    "0000000001-25-000002",
                    "0000000001-25-000003",
                ],
                "primaryDocument": ["", "", ""],
            },
        }

        def fake_get_response_text(url, max_chars):
            requested_urls.append(url)
            return """
            <table><tr class="contractRow">
              <td></td><td></td><td>Example ETF</td><td>EXAM</td>
            </tr></table>
            """

        with patch(
            "sec_filings.fetch_recent_filings_for_cik",
            return_value=recent_filings,
        ), patch("sec_filings.get_response_text", side_effect=fake_get_response_text):
            events = fetch_filing_events(
                date(2025, 1, 1),
                date(2025, 1, 31),
                ciks=["0000000001"],
            )

        requested = "\n".join(requested_urls)
        self.assertIn("000000000125000001", requested)
        self.assertIn("000000000125000002", requested)
        self.assertNotIn("000000000125000003", requested)
        self.assertEqual([event["date"] for event in events], ["2025-01-15"])

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

    def test_latest_snapshot_summarizes_amendment_history(self):
        events = [
            {
                "cik": "0000000001",
                "etf_name": "Example ETF",
                "ticker": "Not Listed",
                "form": "N-1A",
                "date": "2026-01-10",
                "accepted_at": "2026-01-10T12:00:00Z",
            },
            {
                "cik": "0000000001",
                "etf_name": "Example ETF",
                "ticker": "EXAM",
                "form": "485APOS",
                "date": "2026-03-10",
                "accepted_at": "2026-03-10T12:00:00Z",
            },
            {
                "cik": "0000000001",
                "etf_name": "Example ETF",
                "ticker": "EXAM",
                "form": "485BPOS",
                "date": "2026-04-10",
                "accepted_at": "2026-04-10T12:00:00Z",
            },
        ]

        snapshot = derive_latest_fund_rows(events)

        self.assertEqual(snapshot[0]["filing_event_count"], 3)
        self.assertEqual(snapshot[0]["amendment_count"], 2)
        self.assertEqual(
            snapshot[0]["filing_form_history"],
            "N-1A -> 485APOS -> 485BPOS",
        )

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
