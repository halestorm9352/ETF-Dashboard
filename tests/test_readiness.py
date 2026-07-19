import unittest
from datetime import date, datetime

import pandas as pd

from readiness import add_launch_readiness_columns, readiness_status
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


if __name__ == "__main__":
    unittest.main()
