import unittest
from datetime import date, datetime

import pandas as pd

from readiness import (
    EFFECTIVE_AMENDMENT,
    EXISTING_FUND_AMENDMENT,
    INITIAL_REVIEW,
    LAUNCHED_STALE,
    RECENTLY_LAUNCHED,
    ROUTINE_485B_UPDATE,
    TIMING_UNDETECTED,
    UPCOMING_LAUNCH,
    add_launch_readiness_columns,
    readiness_status,
)
from sec_filings import derive_latest_fund_rows
from vehicle_classifier import ETF_VEHICLE, MUTUAL_FUND_SHARE_CLASS


class LaunchReadinessTests(unittest.TestCase):
    TODAY = date(2026, 7, 16)
    EFFECTIVE_DATE = pd.Timestamp("2026-07-15")

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

    def test_485bpos_only_history_is_routine_update(self):
        for history in ("485BPOS", "485BPOS -> 485BPOS"):
            with self.subTest(history=history):
                self.assertEqual(
                    self.readiness(filing_form_history=history),
                    ROUTINE_485B_UPDATE,
                )

    def test_initial_history_followed_by_amendments_is_recently_launched(self):
        self.assertEqual(
            self.readiness(filing_form_history="N-1A -> 485APOS -> 485BPOS"),
            RECENTLY_LAUNCHED,
        )

    def test_485apos_history_is_recently_launched(self):
        self.assertEqual(
            self.readiness(form="485APOS", filing_form_history="485APOS"),
            RECENTLY_LAUNCHED,
        )

    def test_effective_mixed_history_is_effective_amendment(self):
        self.assertEqual(
            self.readiness(filing_form_history="485BPOS -> 485APOS"),
            EFFECTIVE_AMENDMENT,
        )

    def test_authoritative_mapped_mutual_fund_ticker_is_ticker_bearing(self):
        self.assertEqual(
            self.readiness(
                ticker="FLCSX",
                ticker_source="sec_fund_ticker_map",
                vehicle=MUTUAL_FUND_SHARE_CLASS,
            ),
            ROUTINE_485B_UPDATE,
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
            EFFECTIVE_AMENDMENT,
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
        self.assertEqual(result.iloc[0]["launch_readiness"], ROUTINE_485B_UPDATE)
        self.assertFalse(result.iloc[0]["needs_ticker"])

    def test_readiness_columns_preserve_empty_dataframe_shape(self):
        result = add_launch_readiness_columns(pd.DataFrame())

        self.assertTrue(result.empty)
        self.assertIn("filing_stage", result.columns)
        self.assertIn("earliest_auto_effective_date", result.columns)
        self.assertIn("launch_readiness", result.columns)
        self.assertIn("needs_ticker", result.columns)
        self.assertIn("days_to_readiness", result.columns)
        self.assertTrue(
            pd.api.types.is_datetime64_any_dtype(
                result["earliest_auto_effective_date"]
            )
        )

    def test_initial_and_undetected_readiness_states(self):
        cases = (
            ({"form": "N-1A", "filing_form_history": "N-1A"}, INITIAL_REVIEW),
            (
                {"earliest_auto_effective_date": pd.NaT},
                TIMING_UNDETECTED,
            ),
        )

        for overrides, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.readiness(**overrides), expected)

    def test_future_new_pipeline_ticker_is_orthogonal(self):
        rows = pd.DataFrame(
            [
                {
                    "form": "485APOS",
                    "filing_form_history": "485APOS",
                    "ticker": ticker,
                    "vehicle": ETF_VEHICLE,
                    "date": pd.Timestamp("2026-07-01"),
                    "designated_effective_date": "2026-07-17",
                }
                for ticker in ("EXAM", "Not Listed")
            ]
        )

        result = add_launch_readiness_columns(rows, today=self.TODAY)

        self.assertEqual(result["launch_readiness"].tolist(), [UPCOMING_LAUNCH] * 2)
        self.assertEqual(result["needs_ticker"].tolist(), [False, True])

    def test_recently_launched_window_boundary_is_inclusive(self):
        self.assertEqual(
            self.readiness(
                form="485APOS",
                filing_form_history="485APOS",
                earliest_auto_effective_date=pd.Timestamp("2026-06-16"),
            ),
            RECENTLY_LAUNCHED,
        )

    def test_launch_older_than_window_is_stale(self):
        self.assertEqual(
            self.readiness(
                form="485APOS",
                filing_form_history="485APOS",
                earliest_auto_effective_date=pd.Timestamp("2026-06-15"),
            ),
            LAUNCHED_STALE,
        )

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

        self.assertEqual(result.iloc[0]["launch_readiness"], RECENTLY_LAUNCHED)

    def test_missing_series_id_keeps_window_history_behavior(self):
        result = add_launch_readiness_columns(
            self.scoped_485apos(series_id=""),
            series_first_filing_dates={"S000000001": "2020-01-01"},
            search_start_date=date(2026, 5, 1),
            today=date(2026, 7, 20),
        )

        self.assertEqual(result.iloc[0]["launch_readiness"], RECENTLY_LAUNCHED)

    def test_failed_age_lookup_keeps_window_history_behavior(self):
        result = add_launch_readiness_columns(
            self.scoped_485apos(),
            series_first_filing_dates={},
            search_start_date=date(2026, 5, 1),
            today=date(2026, 7, 20),
        )

        self.assertEqual(result.iloc[0]["launch_readiness"], RECENTLY_LAUNCHED)

    def test_old_series_future_pipeline_is_existing_fund_amendment(self):
        rows = self.scoped_485apos()
        rows.loc[0, "effectiveness_days"] = 75

        result = add_launch_readiness_columns(
            rows,
            series_first_filing_dates={"S000000001": "2020-01-01"},
            search_start_date=date(2026, 5, 1),
            today=date(2026, 7, 20),
        )

        self.assertEqual(result.iloc[0]["launch_readiness"], EXISTING_FUND_AMENDMENT)

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
        rows.loc[0, "filing_form_history"] = "485APOS"

        result = add_launch_readiness_columns(
            rows,
            series_first_filing_dates={"S000000001": "2026-02-20"},
            search_start_date=date(2026, 5, 1),
            today=date(2026, 7, 20),
        )

        self.assertEqual(result.iloc[0]["launch_readiness"], EXISTING_FUND_AMENDMENT)


if __name__ == "__main__":
    unittest.main()
