import unittest
from datetime import date, datetime
import json
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from config import (
    INDEX_PAGE_MAX_CHARS,
    PRIMARY_DOCUMENT_MAX_CHARS,
    PRIMARY_IDENTITY_MAX_CHARS,
)
from sec_filings import (
    _enrich_missing_tickers_from_later_filings,
    _enrich_tickers_from_sec_mapping,
    _fetch_filings_for_cik,
    _fetch_filing_rows_for_cik,
    _mapping_validated_prospectus_entries,
    _normalize_vehicle_identity_metadata,
    _row_timestamp,
    derive_latest_fund_rows,
    fetch_sec_fund_ticker_mapping,
    fetch_filing_events,
    fetch_series_registration_date,
    normalize_event_ticker,
)
from sec_parsers import EFFECTIVENESS_SCAN_CAP_CHARS, extract_rule_485_effectiveness
from readiness import LAUNCHED_STALE, readiness_status
from vehicle_classifier import ETF_VEHICLE, MUTUAL_FUND_SHARE_CLASS


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
    def test_exchange_listed_fund_survives_parse_and_snapshot_normalization(self):
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "sec"
            / "wisdomtree_485apos_exchange_listed_primary.html"
        ).read_text(encoding="utf-8")
        cik_data = {
            "filer_name": "WisdomTree Trust",
            "recent": {
                "form": ["485APOS"],
                "filingDate": ["2026-07-09"],
                "acceptanceDateTime": ["2026-07-09T12:00:00Z"],
                "accessionNumber": ["0001214659-26-008405"],
                "primaryDocument": ["pea99872261485apos.htm"],
            },
        }
        index_text = """
        <table class="tableSeries">
          <tr><td class="seriesName">Series S000109282</td>
              <td class="seriesCell"></td>
              <td class="seriesCell">WisdomTree Global Alpha Fund</td></tr>
          <tr class="contractRow"><td>Class/Contract C000280390</td><td></td>
              <td>WisdomTree Global Alpha Fund</td><td></td></tr>
        </table>
        """

        with patch(
            "sec_filings.extract_text",
            side_effect=lambda url, max_chars=300000: (
                fixture if url.endswith("pea99872261485apos.htm") else index_text
            ),
        ), patch("sec_filings.fetch_supporting_document_texts", return_value=[]):
            events = _fetch_filing_rows_for_cik(
                "0001350487",
                datetime(2026, 7, 1),
                datetime(2026, 7, 31, 23, 59, 59),
                cik_data,
            )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["vehicle"], ETF_VEHICLE)
        self.assertNotIn("exchange_listed", events[0])
        snapshot = derive_latest_fund_rows(events)
        self.assertEqual(snapshot[0]["vehicle"], ETF_VEHICLE)

    def test_read_normalization_preserves_known_vehicle_only_for_unknown_result(self):
        rows = [
            {
                "class_name": "Tickerless Example Fund",
                "ticker": "",
                "vehicle": ETF_VEHICLE,
            },
            {
                "class_name": "Mutual Example Fund",
                "ticker": "EXMPX",
                "vehicle": ETF_VEHICLE,
            },
        ]

        normalized = _normalize_vehicle_identity_metadata(rows)

        self.assertEqual(normalized[0]["vehicle"], ETF_VEHICLE)
        self.assertEqual(normalized[1]["vehicle"], MUTUAL_FUND_SHARE_CLASS)

    def test_primary_document_fetch_cap_matches_parser_scan_reach(self):
        self.assertEqual(PRIMARY_DOCUMENT_MAX_CHARS, EFFECTIVENESS_SCAN_CAP_CHARS)
        cik_data = {
            "filer_name": "Example Trust",
            "recent": {
                "form": ["485BPOS", "S-1"],
                "filingDate": ["2026-07-01", "2026-07-02"],
                "acceptanceDateTime": [
                    "2026-07-01T12:00:00Z",
                    "2026-07-02T12:00:00Z",
                ],
                "accessionNumber": [
                    "0000000001-26-000001",
                    "0000000001-26-000002",
                ],
                "primaryDocument": ["485bpos.htm", "s1.htm"],
            },
        }

        with patch("sec_filings.extract_text", return_value="") as extract:
            _fetch_filing_rows_for_cik(
                "0000000001",
                datetime(2026, 7, 1),
                datetime(2026, 7, 2, 23, 59, 59),
                cik_data,
                primary_document_workers=1,
            )

        calls_by_name = {
            call.args[0].rsplit("/", 1)[-1]: call.kwargs.get(
                "max_chars",
                call.args[1] if len(call.args) > 1 else None,
            )
            for call in extract.call_args_list
        }
        self.assertEqual(calls_by_name["485bpos.htm"], PRIMARY_DOCUMENT_MAX_CHARS)
        self.assertEqual(calls_by_name["s1.htm"], PRIMARY_DOCUMENT_MAX_CHARS)
        index_limits = [
            limit
            for name, limit in calls_by_name.items()
            if name.endswith("-index.htm")
        ]
        self.assertTrue(index_limits)
        self.assertTrue(all(limit == INDEX_PAGE_MAX_CHARS for limit in index_limits))

    def test_primary_identity_is_bounded_but_effectiveness_uses_full_document(self):
        cik_data = {
            "filer_name": "Example Trust",
            "recent": {
                "form": ["485BPOS"],
                "filingDate": ["2026-07-17"],
                "acceptanceDateTime": ["2026-07-17T12:00:00Z"],
                "accessionNumber": ["0000000001-26-000001"],
                "primaryDocument": ["example-485bpos.htm"],
            },
        }
        front_matter = "<table><tr><td>Front Matter ETF</td><td>FRNT</td></tr></table>"
        effectiveness = (
            "It is proposed that this filing will become effective "
            "☑ immediately upon filing pursuant to paragraph (b)"
        )
        exhibit = (
            "Investment Sub-Advisory Agreement dated April 25, 2025 "
            "with respect to Junk ETF (JUNK)"
        )
        primary_text = (
            front_matter
            + " " * (400_000 - len(front_matter))
            + effectiveness
            + " " * (500_000 - 400_000 - len(effectiveness))
            + exhibit
        )
        self.assertGreater(primary_text.index(effectiveness), PRIMARY_IDENTITY_MAX_CHARS)
        self.assertGreater(primary_text.index(exhibit), PRIMARY_IDENTITY_MAX_CHARS)

        with patch(
            "sec_filings.extract_text",
            side_effect=lambda url, max_chars=INDEX_PAGE_MAX_CHARS: (
                primary_text if url.endswith("example-485bpos.htm") else ""
            ),
        ):
            rows = _fetch_filing_rows_for_cik(
                "0000000001",
                datetime(2026, 7, 1),
                datetime(2026, 7, 31, 23, 59, 59),
                cik_data,
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["etf_name"], "Front Matter ETF")
        self.assertEqual(rows[0]["ticker"], "FRNT")
        self.assertEqual(rows[0]["effectiveness_basis"], "rule_485_b_immediate")
        self.assertFalse(any(row["ticker"] == "JUNK" for row in rows))
        self.assertFalse(any("Junk ETF" in row["etf_name"] for row in rows))

    def prospectus_pair_pipeline_rows(self, include_pair_mapping=True):
        cik_data = {
            "filer_name": "Example Trust",
            "recent": {
                "form": ["N-1A"],
                "filingDate": ["2026-07-17"],
                "acceptanceDateTime": ["2026-07-17T12:00:00Z"],
                "accessionNumber": ["0000000001-26-000001"],
                "primaryDocument": ["example.htm"],
            },
        }
        index_text = """
        <table class="tableSeries">
          <tr><td class="seriesName">Series S000000999</td>
              <td class="seriesCell"></td><td class="seriesCell">Unrelated ETF</td></tr>
          <tr class="contractRow"><td>Class/Contract C000000999</td><td></td>
              <td>Unrelated ETF</td><td>OTHR</td></tr>
        </table>
        """
        mapping = {
            ("0000000001", "S000000999", "C000000999"): "OTHR",
        }
        if include_pair_mapping:
            mapping[("0000000001", "S000000001", "C000000001")] = "EXAM"

        with patch(
            "sec_filings.extract_text",
            side_effect=lambda url, max_chars=300000: (
                index_text if url.endswith("-index.htm") else "primary"
            ),
        ), patch(
            "sec_filings.extract_named_ticker_pairs",
            return_value=[{"etf_name": "Example ETF", "ticker": "EXAM"}],
        ):
            return _fetch_filing_rows_for_cik(
                "0000000001",
                datetime(2026, 7, 1),
                datetime(2026, 7, 31, 23, 59, 59),
                cik_data,
                ticker_mapping=mapping,
            )

    def test_fetch_pipeline_retains_mapping_validated_pair_with_unrelated_table(self):
        rows = self.prospectus_pair_pipeline_rows()

        self.assertEqual(len(rows), 2)
        mapped_row = next(row for row in rows if row["ticker"] == "EXAM")
        self.assertEqual(mapped_row["series_id"], "S000000001")
        self.assertEqual(mapped_row["class_id"], "C000000001")

    def test_fetch_pipeline_drops_unvalidated_pair_with_unrelated_table(self):
        rows = self.prospectus_pair_pipeline_rows(include_pair_mapping=False)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "OTHR")

    def test_mapping_validated_pair_survives_unrelated_series_with_clean_identity(self):
        mapping = {
            ("0000000001", "S000000001", "C000000001"): "EXAM",
            ("0000000001", "S000000999", "C000000999"): "OTHR",
        }
        unrelated_entries = [
            {
                "series_id": "S000000999",
                "class_id": "C000000999",
                "etf_name": "Unrelated ETF",
            }
        ]
        pairs = [
            {"etf_name": "BZX Example ETF", "ticker": "EXAM"},
            {"etf_name": "Example ETF", "ticker": "EXAM"},
        ]

        retained = _mapping_validated_prospectus_entries(
            "0000000001",
            pairs,
            mapping,
            unrelated_entries,
        )

        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0]["etf_name"], "Example ETF")
        self.assertEqual(retained[0]["series_id"], "S000000001")
        self.assertEqual(retained[0]["class_id"], "C000000001")

    def test_unvalidated_pair_is_dropped_when_series_table_exists(self):
        retained = _mapping_validated_prospectus_entries(
            "0000000001",
            [{"etf_name": "Unvalidated ETF", "ticker": "NOPE"}],
            {("0000000001", "S000000999", "C000000999"): "OTHR"},
            [{"series_id": "S000000999", "class_id": "C000000999"}],
        )

        self.assertEqual(retained, [])

    def test_ambiguous_cik_ticker_mapping_remains_name_scoped(self):
        mapping = {
            ("0000000001", "S000000001", "C000000001"): "DUPL",
            ("0000000001", "S000000002", "C000000002"): "DUPL",
        }

        retained = _mapping_validated_prospectus_entries(
            "0000000001",
            [{"etf_name": "Ambiguous ETF", "ticker": "DUPL"}],
            mapping,
            [{"series_id": "S000000999", "class_id": "C000000999"}],
        )

        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0]["series_id"], "")
        self.assertEqual(retained[0]["class_id"], "")
        self.assertEqual(retained[0]["identity_scope"], "name")

    def test_series_age_lookup_returns_earliest_paginated_filing_date(self):
        first_page = """
        <feed xmlns="http://www.w3.org/2005/Atom">
          <link rel="next" href="https://www.sec.gov/cgi-bin/browse-edgar?start=100&amp;output=atom" />
          <entry><content><filing-date>2025-01-15</filing-date></content></entry>
        </feed>
        """
        last_page = """
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry><content><filing-date>2010-06-30</filing-date></content></entry>
        </feed>
        """
        responses = [Mock(text=first_page), Mock(text=last_page)]

        with patch("sec_filings.get_http_response", side_effect=responses) as get:
            status = fetch_series_registration_date("S000000001")

        self.assertTrue(status["success"])
        self.assertEqual(status["first_filing_date"], "2010-06-30")
        self.assertEqual(get.call_count, 2)

    def test_series_age_lookup_failure_returns_search_status(self):
        with patch(
            "sec_filings.get_http_response",
            side_effect=requests.RequestException("series feed unavailable"),
        ):
            status = fetch_series_registration_date("S000000001")

        self.assertFalse(status["success"])
        self.assertEqual(status["series_id"], "S000000001")
        self.assertEqual(status["first_filing_date"], "")
        self.assertIn("series feed unavailable", status["error_summary"])

    def test_final_sec_rate_limit_marks_cik_failed(self):
        response = requests.Response()
        response.status_code = 429
        error = requests.HTTPError("429 Too Many Requests", response=response)

        with patch("sec_filings.get_http_response", side_effect=error):
            rows, status = _fetch_filings_for_cik(
                "0000000001",
                datetime(2026, 1, 1),
                datetime(2026, 1, 31, 23, 59, 59),
            )

        self.assertEqual(rows, [])
        self.assertFalse(status["success"])
        self.assertIn("429 Too Many Requests", status["error_summary"])

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
        self.assertTrue(mapping.available)

    def test_mapping_fetch_failure_is_visible_without_failing_filer_coverage(self):
        recent_filings = {
            "filer_name": "Example Trust",
            "recent": {
                "form": ["N-1A"],
                "filingDate": ["2026-01-15"],
                "acceptanceDateTime": ["2026-01-15T12:00:00Z"],
                "accessionNumber": ["0000000001-26-000001"],
                "primaryDocument": [""],
            },
        }

        def response_text(url, _max_chars):
            if url.endswith("company_tickers_mf.json"):
                return ""
            return """
            <table><tr class="contractRow">
              <td></td><td></td><td>Example ETF</td><td></td>
            </tr></table>
            """

        with patch(
            "sec_filings.fetch_recent_filings_for_cik",
            return_value=recent_filings,
        ), patch("sec_filings.get_response_text", side_effect=response_text):
            events = fetch_filing_events(
                date(2026, 1, 1),
                date(2026, 1, 31),
                ciks=["0000000001"],
            )

        self.assertEqual(len(events), 1)
        self.assertTrue(events.statuses[0]["success"])
        self.assertFalse(events.mapping_status["available"])
        self.assertIn("no data", events.mapping_status["error_summary"])

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

    def test_later_ticker_enrichment_reclassifies_row_for_launch_readiness(self):
        events = [
            {
                "cik": "0000000001",
                "etf_name": "Example Fund",
                "ticker": "EXAM",
                "date": "2026-06-10",
                "accepted_at": "2026-06-10T12:00:00Z",
            },
            {
                "cik": "0000000001",
                "etf_name": "Example Fund",
                "ticker": "Not Listed",
                "ticker_at_filing": "Not Listed",
                "vehicle": "Other / unknown",
                "form": "485APOS",
                "filing_form_history": "485APOS",
                "earliest_auto_effective_date": datetime(2026, 5, 1),
                "date": "2026-05-01",
                "accepted_at": "2026-05-01T12:00:00Z",
            },
        ]

        enriched = _enrich_missing_tickers_from_later_filings(events)
        older_event = next(row for row in enriched if row["date"] == "2026-05-01")

        self.assertEqual(older_event["ticker"], "EXAM")
        self.assertEqual(older_event["ticker_at_filing"], "Not Listed")
        self.assertEqual(older_event["vehicle"], ETF_VEHICLE)
        self.assertEqual(
            readiness_status(older_event, date(2026, 7, 16)),
            LAUNCHED_STALE,
        )

    def test_identity_scope_flip_resolves_to_one_series_snapshot(self):
        events = [
            {
                "cik": "0000000001",
                "series_id": "S000000001",
                "class_id": "C000000001",
                "series_name": "Example Fund",
                "class_name": "Example Fund",
                "etf_name": "Example Fund",
                "ticker": "Not Listed",
                "identity_scope": "class",
                "form": "N-1A",
                "date": "2026-01-10",
            },
            {
                "cik": "0000000001",
                "series_id": "S000000001",
                "class_id": "C000000001",
                "series_name": "Example Fund",
                "class_name": "Example Fund: Class A",
                "etf_name": "Example Fund",
                "ticker": "FLCSX",
                "identity_scope": "series",
                "form": "485BPOS",
                "date": "2026-04-10",
            },
        ]

        snapshot = derive_latest_fund_rows(events)

        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot[0]["filing_event_count"], 2)
        self.assertEqual(snapshot[0]["identity_scope"], "series")
        self.assertEqual(events[0]["identity_scope"], "class")

    def test_same_day_timestamp_order_uses_naive_utc_for_both_paths(self):
        accepted_event = {
            "cik": "0000000001",
            "etf_name": "Example ETF",
            "ticker": "EXAM",
            "form": "485BPOS",
            "date": "2026-07-01",
            "accepted_at": "2026-07-01T00:30:00+05:00",
        }
        date_only_event = {
            "cik": "0000000001",
            "etf_name": "Example ETF",
            "ticker": "EXAM",
            "form": "485APOS",
            "date": "2026-07-01",
        }

        snapshot = derive_latest_fund_rows([accepted_event, date_only_event])

        self.assertEqual(_row_timestamp(accepted_event), datetime(2026, 6, 30, 19, 30))
        self.assertEqual(_row_timestamp(date_only_event), datetime(2026, 7, 1))
        self.assertEqual(snapshot[0]["form"], "485APOS")
        self.assertEqual(snapshot[0]["filing_form_history"], "485BPOS -> 485APOS")

    def test_snapshot_records_prior_effective_485bpos_for_resolved_identity(self):
        events = [
            {
                "cik": "0000000001",
                "series_id": "S000000001",
                "class_id": "C000000001",
                "etf_name": "Example ETF",
                "class_name": "Example ETF",
                "ticker": "EXAM",
                "form": "485BPOS",
                "effectiveness_days": 0,
                "date": "2026-05-01",
                "accepted_at": "2026-05-01T12:00:00Z",
            },
            {
                "cik": "0000000001",
                "series_id": "S000000001",
                "class_id": "C000000001",
                "etf_name": "Example ETF",
                "class_name": "Example ETF",
                "ticker": "EXAM",
                "form": "485APOS",
                "effectiveness_days": 75,
                "date": "2026-07-17",
                "accepted_at": "2026-07-17T12:00:00Z",
            },
        ]

        snapshot = derive_latest_fund_rows(events)

        self.assertEqual(len(snapshot), 1)
        self.assertTrue(snapshot[0]["prior_effective_485bpos"])
        self.assertEqual(snapshot[0]["filing_form_history"], "485BPOS -> 485APOS")

    def test_designated_date_485bpos_records_prior_effectiveness(self):
        events = [
            {
                "cik": "0000000001",
                "series_id": "S000000001",
                "class_id": "C000000001",
                "etf_name": "Example ETF",
                "class_name": "Example ETF",
                "ticker": "EXAM",
                "form": "485BPOS",
                "designated_effective_date": "April 30, 2026",
                "date": "2026-04-15",
                "accepted_at": "2026-04-15T12:00:00Z",
            },
            {
                "cik": "0000000001",
                "series_id": "S000000001",
                "class_id": "C000000001",
                "etf_name": "Example ETF",
                "class_name": "Example ETF",
                "ticker": "EXAM",
                "form": "485APOS",
                "effectiveness_days": 75,
                "date": "2026-07-17",
                "accepted_at": "2026-07-17T12:00:00Z",
            },
        ]

        snapshot = derive_latest_fund_rows(events)

        self.assertEqual(len(snapshot), 1)
        self.assertTrue(snapshot[0]["prior_effective_485bpos"])


if __name__ == "__main__":
    unittest.main()
