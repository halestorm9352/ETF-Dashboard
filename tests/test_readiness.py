import unittest
from datetime import date

import pandas as pd

from readiness import readiness_status


class LaunchReadinessTests(unittest.TestCase):
    TODAY = date(2026, 7, 16)
    EFFECTIVE_DATE = pd.Timestamp("2026-07-15")
    FUTURE_DATE = pd.Timestamp("2026-07-17")

    def readiness(self, **overrides):
        row = {
            "form": "485BPOS",
            "filing_form_history": "485BPOS",
            "ticker": "EXAM",
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
