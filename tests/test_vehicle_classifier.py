import unittest

from sec_filings import derive_latest_fund_rows
from vehicle_classifier import (
    ETF_VEHICLE,
    MUTUAL_FUND_SHARE_CLASS,
    UNKNOWN_VEHICLE,
    classify_vehicle,
)


class VehicleClassifierTests(unittest.TestCase):
    def test_class_name_and_five_letter_ticker_identify_mutual_share_classes(self):
        cases = (
            {"class_name": "Institutional Class", "ticker": ""},
            {"class_name": "Fidelity Large Cap Stock Fund", "ticker": "FLCSX"},
        )

        for row in cases:
            with self.subTest(row=row):
                self.assertEqual(classify_vehicle(row), MUTUAL_FUND_SHARE_CLASS)

    def test_etf_name_or_short_ticker_identifies_etf(self):
        cases = (
            {"class_name": "SEI Large Cap Factor ETF", "ticker": ""},
            {"class_name": "Example Fund", "ticker": "EXAM"},
        )

        for row in cases:
            with self.subTest(row=row):
                self.assertEqual(classify_vehicle(row), ETF_VEHICLE)

    def test_ambiguous_row_is_unknown(self):
        self.assertEqual(
            classify_vehicle({"class_name": "Example Fund", "ticker": ""}),
            UNKNOWN_VEHICLE,
        )

    def test_exchange_listing_rescues_tickerless_fund_as_etf(self):
        self.assertEqual(
            classify_vehicle(
                {
                    "class_name": "Example Fund",
                    "ticker": "",
                    "exchange_listed": True,
                }
            ),
            ETF_VEHICLE,
        )

    def test_mutual_fund_ticker_precedes_exchange_listing_signal(self):
        self.assertEqual(
            classify_vehicle(
                {
                    "class_name": "Example Fund",
                    "ticker": "EXMPX",
                    "exchange_listed": True,
                }
            ),
            MUTUAL_FUND_SHARE_CLASS,
        )

    def test_false_exchange_listing_leaves_tickerless_fund_unknown(self):
        self.assertEqual(
            classify_vehicle(
                {
                    "class_name": "Example Fund",
                    "ticker": "",
                    "exchange_listed": False,
                }
            ),
            UNKNOWN_VEHICLE,
        )

    def test_parented_class_events_form_one_series_snapshot_row(self):
        base = {
            "cik": "819118",
            "series_id": "S000055364",
            "series_name": "Fidelity Large Cap Stock Fund",
            "etf_name": "Fidelity Large Cap Stock Fund",
            "vehicle": MUTUAL_FUND_SHARE_CLASS,
            "identity_scope": "series",
            "form": "485BPOS",
            "date": "2026-07-01",
            "timestamp": "2026-07-01T12:00:00",
            "accession_number": "0000819118-26-000136",
        }
        events = [
            {
                **base,
                "class_id": "C000174182",
                "class_name": "Fidelity Large Cap Stock Fund",
                "ticker": "FLCSX",
            },
            {
                **base,
                "class_id": "C000259429",
                "class_name": "Fidelity Advisor Large Cap Stock Fund: Class C",
                "ticker": "FLAJX",
            },
        ]

        snapshot = derive_latest_fund_rows(events)

        self.assertEqual(len(events), 2)
        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot[0]["etf_name"], base["series_name"])
        self.assertEqual(snapshot[0]["series_id"], base["series_id"])
        self.assertEqual(snapshot[0]["filing_event_count"], 1)

    def test_dual_vehicle_series_yields_etf_and_parent_mutual_rows(self):
        base = {
            "cik": "0000000001",
            "series_id": "S000000001",
            "series_name": "Example Fund",
            "etf_name": "Example Fund",
            "form": "485BPOS",
            "date": "2026-07-01",
            "accession_number": "0000000001-26-000001",
        }
        events = [
            {
                **base,
                "class_id": "C000000001",
                "class_name": "Example ETF",
                "etf_name": "Example ETF",
                "ticker": "EXMP",
            },
            {
                **base,
                "class_id": "C000000002",
                "class_name": "Example Fund: Class A",
                "ticker": "EXMPX",
            },
            {
                **base,
                "class_id": "C000000003",
                "class_name": "Example Fund: Class C",
                "ticker": "EXMCX",
            },
        ]

        snapshot = derive_latest_fund_rows(events)

        self.assertEqual(len(snapshot), 2)
        self.assertEqual(
            {row["vehicle"] for row in snapshot},
            {ETF_VEHICLE, MUTUAL_FUND_SHARE_CLASS},
        )
        etf_row = next(row for row in snapshot if row["vehicle"] == ETF_VEHICLE)
        mutual_row = next(
            row for row in snapshot if row["vehicle"] == MUTUAL_FUND_SHARE_CLASS
        )
        self.assertEqual(etf_row["identity_scope"], "class")
        self.assertEqual(mutual_row["identity_scope"], "series")
        self.assertEqual(mutual_row["etf_name"], base["series_name"])


if __name__ == "__main__":
    unittest.main()
