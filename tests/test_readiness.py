import unittest
from datetime import date, datetime

import pandas as pd

from readiness import (
    EXISTING_FUND_AMENDMENT,
    add_launch_readiness_columns,
    readiness_status,
)
from sec_filings import derive_latest_fund_rows
from vehicle_classifier import ETF_VEHICLE, MUTUAL_FUND_SHARE_CLASS


class LaunchReadinessTests(unittest.TestCase):
    TODAY = date(2026, 7, 16)
    EFFECTIVE_DATE = pd.Timestamp("2026-07-15")
    FUTURE_DATE = pd.Timestamp("2026-07-17")

    def readiness(self, **overrides):
        row = {
            "form": "485BPOS",
            "filing_form_history": "485BPOS",
            "ticker": "EXAM",
            "vehicle": ETF_VEHICLE,
            "earliest_auto_effective_date": self.EFFECTIVE_DATE,
        }
        row.update(overrides)
        return readiness_status(row, self.TODAY)

    def test_485bpos_only_history_is_effective_update(self):
        for history in ("485BPOS", "485BPOS -> 485BPOS"):
            with self.subTest(history=history):
                self.assertEqual(
                    self.readiness(filing_form_history=history),
                    "Effective (485(b) update)",
                )

    def test_initial_history_followed_by_amendments_is_launch_candidate(self):
        self.assertEqual(
            self.readiness(filing_form_history="N-1A -> 485APOS -> 485BPOS"),
            "Launch candidate",
        )

    def test_485apos_history_is_launch_candidate(self):
        self.assertEqual(
            self.readiness(form="485APOS", filing_form_history="485APOS"),
            "Launch candidate",
        )

    def test_effective_mixed_history_is_effective_amendment(self):
        self.assertEqual(
            self.readiness(filing_form_history="485BPOS -> 485APOS"),
            "Effective (amendment)",
        )

    def test_authoritative_mapped_mutual_fund_ticker_is_ticker_bearing(self):
        self.assertEqual(
            self.readiness(
                ticker="FLCSX",
                ticker_source="sec_fund_ticker_map",
                vehicle=MUTUAL_FUND_SHARE_CLASS,
            ),
            "Effective (485(b) update)",
        )

    def test_mutual_fund_share_class_is_not_a_launch_candidate(self):
        self.assertEqual(
            self.readiness(
                form="485APOS",
                filing_form_history="485APOS",
                ticker="FLCSX",
                ticker_source="sec_fund_ticker_map",
                vehicle=MUTUAL_FUND_SHARE_CLASS,
            ),
            "Effective (amendment)",
        )

    def test_readiness_columns_retain_mutual_fund_rows(self):
        rows = pd.DataFrame(
            [
                {
                    "form": "485BPOS",
                    "filing_form_history": "485BPOS",
                    "ticker": "FLCSX",
                    "ticker_source": "sec_fund_ticker_map",
                    "vehicle": MUTUAL_FUND_SHARE_CLASS,
                    "date": pd.Timestamp(datetime.today().date()),
                    "effectiveness_days": 0,
                }
            ]
        )

        result = add_launch_readiness_columns(rows)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["vehicle"], MUTUAL_FUND_SHARE_CLASS)
        self.assertEqual(result.iloc[0]["launch_readiness"], "Effective (485(b) update)")

    def test_readiness_columns_preserve_empty_dataframe_shape(self):
        result = add_launch_readiness_columns(pd.DataFrame())

        self.assertTrue(result.empty)
        self.assertIn("filing_stage", result.columns)
        self.assertIn("earliest_auto_effective_date", result.columns)
        self.assertIn("launch_readiness", result.columns)
        self.assertIn("days_to_readiness", result.columns)
        self.assertTrue(
            pd.api.types.is_datetime64_any_dtype(
                result["earliest_auto_effective_date"]
            )
        )

    def test_existing_readiness_states_are_unchanged(self):
        cases = (
            ({"form": "N-1A", "filing_form_history": "N-1A"}, "Initial review"),
            (
                {"earliest_auto_effective_date": pd.NaT},
                "Timing not detected",
            ),
            ({"ticker": "Not Listed"}, "Needs ticker"),
            (
                {"earliest_auto_effective_date": self.FUTURE_DATE},
                "Waiting on effectiveness",
            ),
        )

        for overrides, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.readiness(**overrides), expected)

    def scoped_485apos(self, series_id="S000000001"):
        return pd.DataFrame(
            [
                {
                    "form": "485APOS",
                    "filing_form_history": "485APOS",
                    "ticker": "EXAM",
                    "vehicle": ETF_VEHICLE,
                    "series_id": series_id,
                    "date": pd.Timestamp("2026-07-01"),
                    "effectiveness_days": 0,
                }
            ]
        )

    def test_old_series_485apos_is_existing_fund_amendment(self):
        result = add_launch_readiness_columns(
            self.scoped_485apos(),
            series_first_filing_dates={"S000000001": "2020-01-01"},
            search_start_date=date(2026, 5, 1),
            today=date(2026, 7, 20),
        )

        self.assertEqual(result.iloc[0]["launch_readiness"], EXISTING_FUND_AMENDMENT)

    def test_young_series_485apos_keeps_pipeline_status(self):
        result = add_launch_readiness_columns(
            self.scoped_485apos(),
            series_first_filing_dates={"S000000001": "2026-01-01"},
            search_start_date=date(2026, 5, 1),
            today=date(2026, 7, 20),
        )

        self.assertEqual(result.iloc[0]["launch_readiness"], "Launch candidate")

    def test_missing_series_id_keeps_window_history_behavior(self):
        result = add_launch_readiness_columns(
            self.scoped_485apos(series_id=""),
            series_first_filing_dates={"S000000001": "2020-01-01"},
            search_start_date=date(2026, 5, 1),
            today=date(2026, 7, 20),
        )

        self.assertEqual(result.iloc[0]["launch_readiness"], "Launch candidate")

    def test_failed_age_lookup_keeps_window_history_behavior(self):
        result = add_launch_readiness_columns(
            self.scoped_485apos(),
            series_first_filing_dates={},
            search_start_date=date(2026, 5, 1),
            today=date(2026, 7, 20),
        )

        self.assertEqual(result.iloc[0]["launch_readiness"], "Launch candidate")

    def test_prior_effective_485bpos_overrides_young_series_age(self):
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
                "vehicle": ETF_VEHICLE,
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
                "vehicle": ETF_VEHICLE,
            },
        ]
        rows = pd.DataFrame(derive_latest_fund_rows(events))
        rows["date"] = pd.to_datetime(rows["date"])

        self.assertTrue(rows.iloc[0]["prior_effective_485bpos"])

        result = add_launch_readiness_columns(
            rows,
            series_first_filing_dates={"S000000001": "2026-02-20"},
            search_start_date=date(2026, 5, 1),
            today=date(2026, 7, 20),
        )

        self.assertEqual(result.iloc[0]["launch_readiness"], EXISTING_FUND_AMENDMENT)


if __name__ == "__main__":
    unittest.main()
