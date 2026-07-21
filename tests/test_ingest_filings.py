from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.ingest_filings import main, run_ingest
from store import (
    get_series_registry,
    is_filing_processed,
    load_events,
    open_store,
    record_ingest_run,
    record_processed_filing,
)
from tests.test_store import sample_event


def success_status(cik, row_count=1):
    return {
        "cik": cik,
        "filer": f"Trust {cik}",
        "status": "success",
        "success": True,
        "failed": False,
        "row_count": row_count,
        "error_summary": "",
    }


def failure_status(cik, message="SEC unavailable"):
    return {
        "cik": cik,
        "filer": f"Trust {cik}",
        "status": "failed",
        "success": False,
        "failed": True,
        "row_count": 0,
        "error_summary": message,
    }


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.store_path = Path(self.temp_dir.name) / "etf_dash.sqlite"
        self.handle = open_store(self.store_path)

    def tearDown(self):
        self.handle.close()
        self.temp_dir.cleanup()

    @patch("scripts.ingest_filings.fetch_series_registration_date")
    @patch("scripts.ingest_filings.fetch_sec_fund_ticker_mapping", return_value={})
    @patch("scripts.ingest_filings._fetch_filings_for_cik")
    def test_reingest_skips_processed_accession_and_honors_overlap(
        self,
        fetch_cik,
        _fetch_mapping,
        fetch_series_date,
    ):
        event = sample_event(series_id="", class_id="", identity_scope="name")
        bounds = []

        def fake_fetch(cik, start_bound, end_bound, **_kwargs):
            bounds.append((start_bound.date(), end_bound.date()))
            return [dict(event)], success_status(cik)

        fetch_cik.side_effect = fake_fetch
        fetch_series_date.return_value = {"success": False}
        first = run_ingest(
            self.handle,
            mode="backfill",
            ciks=[event["cik"]],
            today=date(2026, 7, 20),
        )
        second = run_ingest(
            self.handle,
            mode="incremental",
            ciks=[event["cik"]],
            today=date(2026, 7, 21),
        )

        self.assertEqual(first["events_added"], 1)
        self.assertEqual(second["events_added"], 0)
        self.assertEqual(second["filings_processed"], 0)
        self.assertEqual(second["filings_skipped"], 1)
        self.assertEqual(bounds[1], (date(2026, 7, 17), date(2026, 7, 21)))
        self.assertEqual(len(load_events(self.handle, "2026-01-01", "2026-12-31")), 1)

    @patch("scripts.ingest_filings.fetch_series_registration_date")
    @patch("scripts.ingest_filings.fetch_sec_fund_ticker_mapping", return_value={})
    @patch("scripts.ingest_filings._fetch_filings_for_cik")
    def test_series_registry_resolves_success_and_retries_failure(
        self,
        fetch_cik,
        _fetch_mapping,
        fetch_series_date,
    ):
        events = [
            sample_event(
                event_id="one",
                accession_number="one",
                series_id="S000000001",
                class_id="C000000001",
            ),
            sample_event(
                event_id="two",
                accession_number="two",
                series_id="S000000002",
                class_id="C000000002",
            ),
        ]
        fetch_cik.return_value = (events, success_status("0000000001", 2))
        fetch_series_date.side_effect = [
            {
                "series_id": "S000000001",
                "success": True,
                "first_filing_date": "2025-01-01",
                "error_summary": "",
            },
            {
                "series_id": "S000000002",
                "success": False,
                "first_filing_date": "",
                "error_summary": "timeout",
            },
        ]

        result = run_ingest(
            self.handle,
            mode="backfill",
            ciks=["0000000001"],
            today=date(2026, 7, 20),
        )

        self.assertEqual(get_series_registry(self.handle), {"S000000001": "2025-01-01"})
        self.assertEqual(result["series_resolved"], 1)
        self.assertEqual(result["series_unresolved"][0]["series_id"], "S000000002")

    @patch("scripts.ingest_filings.fetch_series_registration_date")
    @patch("scripts.ingest_filings.fetch_sec_fund_ticker_mapping", return_value={})
    @patch("scripts.ingest_filings._fetch_filings_for_cik")
    def test_partial_failure_is_recorded_but_returns_success(
        self,
        fetch_cik,
        _fetch_mapping,
        _fetch_series,
    ):
        event = sample_event(series_id="", class_id="", identity_scope="name")
        fetch_cik.side_effect = [
            ([event], success_status("0000000001")),
            ([], failure_status("0000000002", "HTTP 429")),
        ]

        result = run_ingest(
            self.handle,
            mode="backfill",
            ciks=["0000000001", "0000000002"],
            today=date(2026, 7, 20),
        )
        stored_run = self.handle.execute(
            "SELECT * FROM ingest_runs WHERE run_id = ?",
            (result["run_id"],),
        ).fetchone()

        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(stored_run["ciks_failed"], 1)
        self.assertIn("Trust 0000000002: HTTP 429", stored_run["error_summary"])

    @patch("scripts.ingest_filings.print")
    @patch("scripts.ingest_filings.fetch_sec_fund_ticker_mapping", return_value={})
    @patch("scripts.ingest_filings._fetch_filings_for_cik")
    def test_all_cik_failure_main_returns_nonzero_and_records_run(
        self,
        fetch_cik,
        _fetch_mapping,
        _print,
    ):
        fetch_cik.side_effect = lambda cik, *_args, **_kwargs: (
            [],
            failure_status(cik, "HTTP 403"),
        )
        self.handle.close()

        exit_code = main(
            ["--backfill", "--store", str(self.store_path)],
            ciks=["0000000001", "0000000002"],
            today=date(2026, 7, 20),
        )
        self.handle = open_store(self.store_path)
        stored_run = self.handle.execute(
            "SELECT * FROM ingest_runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone()

        self.assertEqual(exit_code, 1)
        self.assertEqual(stored_run["ciks_attempted"], 2)
        self.assertEqual(stored_run["ciks_failed"], 2)
        self.assertIn("HTTP 403", stored_run["error_summary"])

    def test_incremental_bound_uses_last_successful_end_minus_three_days(self):
        record_ingest_run(
            self.handle,
            {
                "mode": "backfill",
                "started_at": "2026-07-10T10:00:00+00:00",
                "completed_at": "2026-07-10T11:00:00+00:00",
                "start_bound": "2025-07-10",
                "end_bound": "2026-07-10",
                "ciks_attempted": 1,
                "ciks_failed": 0,
                "filings_processed": 1,
                "events_added": 1,
                "error_summary": "",
            },
        )
        processed = sample_event(
            event_id="processed",
            accession_number="processed",
            series_id="",
            class_id="",
            identity_scope="name",
        )
        record_processed_filing(
            self.handle,
            "processed",
            processed["cik"],
            processed["form"],
            processed["date"],
            12,
            1,
        )
        new_event = sample_event(
            event_id="new",
            accession_number="new",
            series_id="",
            class_id="",
            identity_scope="name",
        )
        captured = {}

        def fake_fetch(cik, start_bound, end_bound, **_kwargs):
            captured["bounds"] = (start_bound.date(), end_bound.date())
            return [processed, new_event], success_status(cik, 2)

        with (
            patch("scripts.ingest_filings._fetch_filings_for_cik", side_effect=fake_fetch),
            patch("scripts.ingest_filings.fetch_sec_fund_ticker_mapping", return_value={}),
        ):
            result = run_ingest(
                self.handle,
                mode="incremental",
                ciks=["0000000001"],
                today=date(2026, 7, 12),
            )

        self.assertEqual(captured["bounds"], (date(2026, 7, 7), date(2026, 7, 12)))
        self.assertTrue(is_filing_processed(self.handle, "new"))
        self.assertEqual(result["filings_skipped"], 1)
        self.assertEqual(result["filings_processed"], 1)


if __name__ == "__main__":
    unittest.main()
