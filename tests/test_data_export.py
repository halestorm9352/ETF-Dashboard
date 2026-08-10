from datetime import date
import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from config import CIKS
from data_export import export_events_csv, export_snapshot_csv, read_store_bytes
from store import (
    EVENT_FIELDS,
    open_store,
    upsert_events,
    upsert_series_registration,
)


def event(**overrides):
    row = {
        "event_id": "0000000001-26-000001:C000000001",
        "accession_number": "0000000001-26-000001",
        "cik": CIKS[0],
        "form": "485APOS",
        "date": "2026-06-01",
        "accepted_at": "2026-06-01T12:00:00Z",
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
        "effectiveness_basis": "rule_485_a2_75_days",
        "effectiveness_days": 75,
        "designated_effective_date": "",
        "effectiveness_label": "75 days after filing",
    }
    row.update(overrides)
    return row


class DataExportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.store_path = Path(self.temp_dir.name) / "etf_dash.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def seed_store(self, events):
        handle = open_store(self.store_path)
        try:
            upsert_events(handle, events, parser_version=15)
            upsert_series_registration(
                handle,
                "S000000001",
                CIKS[0],
                "2026-01-15",
                "test",
            )
        finally:
            handle.close()

    def test_export_events_csv_uses_event_fields_and_all_rows(self):
        self.seed_store(
            [
                event(),
                event(
                    event_id="0000000001-26-000002:C000000002",
                    accession_number="0000000001-26-000002",
                    series_id="S000000002",
                    class_id="C000000002",
                    etf_name="Second ETF",
                ),
            ]
        )

        rows = list(
            csv.reader(StringIO(export_events_csv(self.store_path).decode("utf-8")))
        )

        self.assertEqual(rows[0], list(EVENT_FIELDS))
        self.assertEqual(len(rows) - 1, 2)

    def test_export_snapshot_csv_has_derived_columns_and_one_identity_row(self):
        self.seed_store(
            [
                event(),
                event(
                    event_id="0000000001-26-000002:C000000001",
                    accession_number="0000000001-26-000002",
                    date="2026-07-01",
                    accepted_at="2026-07-01T12:00:00Z",
                ),
            ]
        )

        rows = list(
            csv.DictReader(
                StringIO(
                    export_snapshot_csv(
                        self.store_path,
                        today=date(2026, 8, 10),
                    ).decode("utf-8")
                )
            )
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["vehicle"], "ETF")
        self.assertIn("themes", rows[0])
        self.assertIn("launch_readiness", rows[0])
        self.assertIn("effectiveness_basis", rows[0])
        self.assertIn("earliest_auto_effective_date", rows[0])

    def test_read_store_bytes_reads_existing_store_and_handles_missing(self):
        self.seed_store([event()])

        self.assertEqual(read_store_bytes(self.store_path), self.store_path.read_bytes())
        self.assertIsNone(read_store_bytes(self.store_path.with_name("missing.sqlite")))

    def test_missing_store_returns_none_from_all_exporters(self):
        missing = self.store_path.with_name("missing.sqlite")

        self.assertIsNone(read_store_bytes(missing))
        self.assertIsNone(export_events_csv(missing))
        self.assertIsNone(export_snapshot_csv(missing, today=date(2026, 8, 10)))
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
