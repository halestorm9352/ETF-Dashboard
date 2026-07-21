import importlib
import sqlite3
import sys
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from sec_filings import (
    _enrich_missing_tickers_from_later_filings,
    derive_latest_fund_rows,
)
from store import (
    EVENT_FIELDS,
    SCHEMA_VERSION,
    get_last_successful_ingest,
    get_series_registry,
    is_filing_processed,
    load_events,
    open_store,
    record_ingest_run,
    record_processed_filing,
    upsert_events,
    upsert_series_registration,
)


def sample_event(**overrides):
    event = {
        "event_id": "0000000001-26-000001:C000000001",
        "accession_number": "0000000001-26-000001",
        "cik": "0000000001",
        "form": "485APOS",
        "date": "2026-07-01",
        "accepted_at": "2026-07-01T12:30:00Z",
        "etf_name": "Example ETF",
        "class_name": "Example ETF",
        "series_name": "Example ETF",
        "series_id": "S000000001",
        "class_id": "C000000001",
        "ticker": "EXAM",
        "ticker_at_filing": "Not Listed",
        "ticker_source": "sec_fund_ticker_map",
        "vehicle": "ETF",
        "identity_scope": "class",
        "filer": "Example Trust",
        "link": "https://www.sec.gov/example",
        "effectiveness_basis": "rule_485_a2_75_days",
        "effectiveness_days": 75,
        "designated_effective_date": "",
        "effectiveness_label": "75 days after filing",
    }
    event.update(overrides)
    return event


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.store_path = Path(self.temp_dir.name) / "etf_dash.sqlite"
        self.handle = open_store(self.store_path)

    def tearDown(self):
        self.handle.close()
        self.temp_dir.cleanup()

    def test_event_round_trip_preserves_contract_fields_and_filters(self):
        expected = sample_event()
        outside = sample_event(
            event_id="outside",
            accession_number="outside",
            cik="0000000002",
            date="2026-06-01",
            effectiveness_days="",
        )
        counts = upsert_events(self.handle, [expected, outside], parser_version=12)

        loaded = load_events(
            self.handle,
            "2026-07-01",
            "2026-07-31",
            ciks=["0000000001"],
        )

        self.assertEqual(counts, {"events_added": 2, "events_updated": 0})
        self.assertEqual(loaded, [expected])
        self.assertEqual(set(loaded[0]), set(EVENT_FIELDS))

    def test_effectiveness_days_preserves_none_empty_and_integer_values(self):
        events = [
            sample_event(
                event_id="none",
                accession_number="none",
                effectiveness_days=None,
            ),
            sample_event(
                event_id="empty",
                accession_number="empty",
                effectiveness_days="",
            ),
            sample_event(
                event_id="integer",
                accession_number="integer",
                effectiveness_days=75,
            ),
        ]
        upsert_events(self.handle, events, parser_version=12)

        loaded = {
            event["event_id"]: event["effectiveness_days"]
            for event in load_events(self.handle, "2026-07-01", "2026-07-31")
        }

        self.assertIsNone(loaded["none"])
        self.assertEqual(loaded["empty"], "")
        self.assertEqual(loaded["integer"], 75)

    def test_event_upsert_and_processed_accession_are_idempotent(self):
        event = sample_event()
        first = upsert_events(self.handle, [event], parser_version=12)
        second = upsert_events(self.handle, [event], parser_version=12)
        record_processed_filing(
            self.handle,
            event["accession_number"],
            event["cik"],
            event["form"],
            event["date"],
            12,
            1,
        )
        record_processed_filing(
            self.handle,
            event["accession_number"],
            event["cik"],
            event["form"],
            event["date"],
            12,
            1,
        )

        self.assertEqual(first["events_added"], 1)
        self.assertEqual(second["events_added"], 0)
        self.assertTrue(is_filing_processed(self.handle, event["accession_number"]))
        self.assertEqual(
            self.handle.execute("SELECT COUNT(*) FROM filing_events").fetchone()[0],
            1,
        )
        self.assertEqual(
            self.handle.execute("SELECT COUNT(*) FROM processed_filings").fetchone()[0],
            1,
        )

    def test_store_is_transparent_to_existing_enrichment_and_snapshot_pipeline(self):
        events = [
            sample_event(
                event_id="early",
                accession_number="early",
                date="2026-07-01",
                accepted_at="2026-07-01T12:00:00Z",
                series_id="",
                class_id="",
                ticker="Not Listed",
                ticker_at_filing="Not Listed",
                ticker_source="not_listed",
                identity_scope="name",
            ),
            sample_event(
                event_id="late",
                accession_number="late",
                form="485BPOS",
                date="2026-07-15",
                accepted_at="2026-07-15T12:00:00Z",
                series_id="",
                class_id="",
                ticker="EXAM",
                ticker_at_filing="EXAM",
                ticker_source="filing",
                identity_scope="name",
                effectiveness_days=0,
            ),
        ]
        upsert_events(self.handle, events, parser_version=12)
        loaded = load_events(self.handle, "2026-07-01", "2026-07-31")

        memory_snapshot = derive_latest_fund_rows(
            _enrich_missing_tickers_from_later_filings([dict(row) for row in events])
        )
        stored_snapshot = derive_latest_fund_rows(
            _enrich_missing_tickers_from_later_filings(loaded)
        )

        self.assertEqual(stored_snapshot, memory_snapshot)

    def test_series_registry_and_ingest_run_round_trip(self):
        upsert_series_registration(
            self.handle,
            "s000000001",
            "0000000001",
            "2025-01-02",
            "sec_browse_edgar_atom",
        )
        run = {
            "mode": "backfill",
            "started_at": "2026-07-20T10:00:00+00:00",
            "completed_at": "2026-07-20T10:05:00+00:00",
            "start_bound": "2025-07-20",
            "end_bound": "2026-07-20",
            "ciks_attempted": 2,
            "ciks_failed": 1,
            "filings_processed": 3,
            "events_added": 4,
            "error_summary": "Example Trust: timeout",
        }
        run_id = record_ingest_run(self.handle, run)

        self.assertEqual(get_series_registry(self.handle), {"S000000001": "2025-01-02"})
        self.assertEqual(get_last_successful_ingest(self.handle)["run_id"], run_id)
        self.assertEqual(
            get_last_successful_ingest(self.handle)["error_summary"],
            "Example Trust: timeout",
        )

    def test_schema_version_mismatch_raises_clear_error(self):
        self.handle.execute(
            "UPDATE store_meta SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION + 1),),
        )
        self.handle.commit()
        self.handle.close()

        with self.assertRaisesRegex(RuntimeError, "schema version mismatch"):
            open_store(self.store_path)

        self.handle = sqlite3.connect(":memory:")

    def test_importing_store_does_not_import_streamlit(self):
        sys.modules.pop("store", None)
        sys.modules.pop("streamlit", None)

        importlib.import_module("store")

        self.assertNotIn("streamlit", sys.modules)


if __name__ == "__main__":
    unittest.main()
