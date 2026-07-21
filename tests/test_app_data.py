from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from app_data import (
    load_store_first_filing_events,
    load_store_series_registry,
    resolve_series_registration_status,
)
from sec_filings import FilingEventResults, derive_latest_fund_rows, finalize_event_rows
from store import (
    open_store,
    record_ingest_run,
    upsert_events,
    upsert_series_registration,
)


def event(**overrides):
    row = {
        "event_id": "0000000001-26-000001:C000000001",
        "accession_number": "0000000001-26-000001",
        "cik": "0000000001",
        "form": "485BPOS",
        "date": "2026-07-01",
        "accepted_at": "2026-07-01T12:00:00Z",
        "etf_name": "Example ETF",
        "class_name": "Example ETF",
        "series_name": "Example ETF",
        "series_id": "S000000001",
        "class_id": "C000000001",
        "ticker": "EXAM",
        "ticker_at_filing": "EXAM",
        "ticker_source": "filing",
        "vehicle": "ETF",
        "identity_scope": "class",
        "filer": "Example Trust",
        "link": "https://www.sec.gov/example",
        "effectiveness_basis": "rule_485_b_immediate",
        "effectiveness_days": 0,
        "designated_effective_date": "",
        "effectiveness_label": "Effective immediately under Rule 485(b)",
    }
    row.update(overrides)
    return row


class AppStoreRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.store_path = Path(self.temp_dir.name) / "etf_dash.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def seed_store(self, events, *, end_bound="2026-07-20"):
        handle = open_store(self.store_path)
        try:
            upsert_events(handle, events, parser_version=12)
            record_ingest_run(
                handle,
                {
                    "mode": "backfill",
                    "started_at": "2026-07-20T10:00:00+00:00",
                    "completed_at": "2026-07-20T11:00:00+00:00",
                    "start_bound": "2025-07-20",
                    "end_bound": end_bound,
                    "ciks_attempted": 1,
                    "ciks_failed": 0,
                    "filings_processed": len(events),
                    "events_added": len(events),
                    "error_summary": "",
                },
            )
        finally:
            handle.close()

    def test_store_only_offline_load_matches_pure_event_pipeline(self):
        events = [
            event(),
            event(
                event_id="0000000001-26-000002:C000000001",
                accession_number="0000000001-26-000002",
                form="485APOS",
                date="2026-07-10",
                accepted_at="2026-07-10T12:00:00Z",
                effectiveness_basis="rule_485_a2_75_days",
                effectiveness_days=75,
                effectiveness_label="75 days after filing",
            ),
        ]
        self.seed_store(events)
        network = Mock(side_effect=AssertionError("network must not be called"))

        stored_results, notices = load_store_first_filing_events(
            self.store_path,
            date(2026, 7, 1),
            date(2026, 7, 15),
            ["0000000001"],
            live_fetch=network,
        )
        stored_snapshot = derive_latest_fund_rows(stored_results)
        pure_snapshot = derive_latest_fund_rows(
            finalize_event_rows(
                [dict(row) for row in events],
                date(2026, 7, 1),
                date(2026, 7, 15),
            )
        )

        self.assertEqual(stored_snapshot, pure_snapshot)
        self.assertEqual(notices, [])
        self.assertEqual(network.call_count, 0)
        self.assertEqual(stored_results.statuses[0]["source"], "store")

    def test_top_up_merges_and_deduplicates_overlap_by_event_id(self):
        stored = event(date="2026-07-08", accepted_at="2026-07-08T12:00:00Z")
        self.seed_store([stored], end_bound="2026-07-10")
        overlap_live = dict(stored)
        tail = event(
            event_id="0000000001-26-000003:C000000002",
            accession_number="0000000001-26-000003",
            date="2026-07-12",
            accepted_at="2026-07-12T12:00:00Z",
            etf_name="Tail ETF",
            class_name="Tail ETF",
            series_name="Tail ETF",
            series_id="S000000002",
            class_id="C000000002",
            ticker="TAIL",
            ticker_at_filing="TAIL",
        )
        top_up = FilingEventResults(
            [overlap_live, tail],
            statuses=[
                {
                    "cik": "0000000001",
                    "filer": "Example Trust",
                    "status": "success",
                    "success": True,
                    "failed": False,
                    "row_count": 2,
                    "error_summary": "",
                }
            ],
            mapping_status={"available": True, "error_summary": ""},
        )
        live_fetch = Mock(return_value=top_up)

        merged, notices = load_store_first_filing_events(
            self.store_path,
            date(2026, 7, 1),
            date(2026, 7, 12),
            ["0000000001"],
            live_fetch=live_fetch,
        )
        expected = finalize_event_rows(
            [dict(overlap_live), dict(tail)],
            date(2026, 7, 1),
            date(2026, 7, 12),
        )

        self.assertEqual(len(merged), 2)
        self.assertEqual(len({row["event_id"] for row in merged}), 2)
        self.assertEqual(merged, expected)
        self.assertEqual(notices, [])
        live_fetch.assert_called_once_with(
            date(2026, 7, 7),
            date(2026, 7, 12),
            ciks=("0000000001",),
        )

    def test_missing_store_uses_pure_live_path(self):
        live_results = FilingEventResults([event()])
        live_fetch = Mock(return_value=live_results)

        results, notices = load_store_first_filing_events(
            self.store_path,
            date(2026, 7, 1),
            date(2026, 7, 2),
            ["0000000001"],
            live_fetch=live_fetch,
        )

        self.assertIs(results, live_results)
        self.assertEqual(notices, [])
        live_fetch.assert_called_once_with(
            date(2026, 7, 1),
            date(2026, 7, 2),
            ciks=("0000000001",),
        )

    def test_offline_top_up_returns_stored_rows_and_warning(self):
        stored = event(date="2026-07-08")
        self.seed_store([stored], end_bound="2026-07-10")

        results, notices = load_store_first_filing_events(
            self.store_path,
            date(2026, 7, 1),
            date(2026, 7, 12),
            ["0000000001"],
            live_fetch=Mock(side_effect=ConnectionError("offline")),
        )

        self.assertEqual([row["event_id"] for row in results], [stored["event_id"]])
        self.assertEqual(notices[0]["level"], "warning")
        self.assertIn("showing stored coverage only", notices[0]["message"])
        self.assertFalse(results.statuses[0]["success"])

    def test_series_registry_hit_avoids_live_and_miss_falls_back_once(self):
        handle = open_store(self.store_path)
        try:
            upsert_series_registration(
                handle,
                "S000000001",
                "0000000001",
                "2025-01-15",
                "sec_browse_edgar_atom",
            )
        finally:
            handle.close()
        registry = load_store_series_registry(self.store_path)
        live_fetch = Mock(
            return_value={
                "series_id": "S000000002",
                "success": True,
                "first_filing_date": "2026-01-15",
                "error_summary": "",
            }
        )

        stored_status = resolve_series_registration_status(
            "s000000001",
            registry,
            live_fetch=live_fetch,
        )
        live_status = resolve_series_registration_status(
            "S000000002",
            registry,
            live_fetch=live_fetch,
        )

        self.assertEqual(
            stored_status,
            {
                "series_id": "S000000001",
                "success": True,
                "first_filing_date": "2025-01-15",
                "error_summary": "",
            },
        )
        self.assertEqual(live_status["first_filing_date"], "2026-01-15")
        live_fetch.assert_called_once_with("S000000002")


if __name__ == "__main__":
    unittest.main()
