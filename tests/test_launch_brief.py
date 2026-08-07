from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from readiness import INITIAL_REVIEW, UPCOMING_LAUNCH
from scripts.generate_launch_brief import (
    compute_delta,
    generate_brief,
    pipeline_identity,
    render_brief,
)
from sec_parsers import PARSER_VERSION
from store import open_store, upsert_events
from tests.test_store import sample_event


def brief_row(**overrides):
    row = {
        "cik": "0000000001",
        "series_id": "S000000001",
        "class_id": "C000000001",
        "etf_name": "Example Future ETF",
        "ticker": "Not Listed",
        "needs_ticker": True,
        "filer": "Example Trust",
        "theme": "Thematic Equity",
        "vehicle": "ETF",
        "form": "485APOS",
        "earliest_auto_effective_date": "2026-09-01",
        "days_to_readiness": 25,
        "launch_readiness": UPCOMING_LAUNCH,
    }
    row.update(overrides)
    return row


class LaunchBriefTests(unittest.TestCase):
    TODAY = date(2026, 8, 7)

    def test_compute_delta_returns_new_rows_and_current_identity_set(self):
        existing = brief_row()
        added = brief_row(
            series_id="S000000002",
            class_id="C000000002",
            etf_name="New Future ETF",
        )

        new_rows, current_ids = compute_delta(
            [existing, added],
            {pipeline_identity(existing)},
        )

        self.assertEqual(new_rows, [added])
        self.assertEqual(
            current_ids,
            {pipeline_identity(existing), pipeline_identity(added)},
        )

    def test_render_brief_counts_and_new_fund_details(self):
        new_fund = brief_row()
        current = [
            new_fund,
            brief_row(
                series_id="S000000002",
                class_id="C000000002",
                etf_name="Listed Future ETF",
                ticker="LIST",
                needs_ticker=False,
                theme="Fixed Income / Credit",
            ),
            brief_row(
                series_id="S000000003",
                class_id="C000000003",
                etf_name="Initial Registration ETF",
                filer="Another Trust",
                theme="Thematic Equity",
                form="N-1A",
                earliest_auto_effective_date="",
                days_to_readiness="",
                launch_readiness=INITIAL_REVIEW,
            ),
        ]

        markdown = render_brief(
            current,
            [new_fund],
            self.TODAY,
            False,
            previous_as_of="2026-08-06T00:00:00Z",
        )

        self.assertIn("3 funds (2 upcoming, 1 initial review)", markdown)
        self.assertIn("**New since the last brief:** 1.", markdown)
        self.assertIn("- Example Trust: 2", markdown)
        self.assertIn("- Thematic Equity: 2", markdown)
        self.assertIn("**Example Future ETF**", markdown)
        self.assertIn("Not Listed (ticker needed)", markdown)
        self.assertIn("Effective date: 2026-09-01", markdown)
        self.assertIn("Days to effective: 25", markdown)

    def test_render_brief_reports_zero_new_since_previous_date(self):
        markdown = render_brief(
            [brief_row()],
            [],
            self.TODAY,
            False,
            previous_as_of="2026-08-06T00:00:00Z",
        )

        self.assertIn("**New since the last brief:** 0.", markdown)
        self.assertIn("No new pipeline entries since 2026-08-06.", markdown)

    def test_render_brief_frames_first_run_as_baseline(self):
        markdown = render_brief(
            [brief_row()],
            [brief_row()],
            self.TODAY,
            True,
        )

        self.assertIn("**Baseline brief:** no prior state was found", markdown)
        self.assertNotIn("New since the last brief", markdown)

    def test_generate_brief_writes_artifacts_and_second_run_has_no_new_rows(self):
        with TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "etf_dash.sqlite"
            handle = open_store(store_path)
            try:
                upsert_events(
                    handle,
                    [
                        sample_event(
                            cik="0000000001",
                            date="2026-07-20",
                            accepted_at="2026-07-20T12:00:00Z",
                            ticker="Not Listed",
                            ticker_at_filing="Not Listed",
                            ticker_source="",
                            effectiveness_days=75,
                            effectiveness_label="75 days after filing",
                        )
                    ],
                    parser_version=PARSER_VERSION,
                )
            finally:
                handle.close()

            with patch(
                "scripts.generate_launch_brief.CIKS",
                ["0000000001"],
            ):
                first = generate_brief(store_path, date(2026, 7, 20))
                second = generate_brief(store_path, date(2026, 7, 20))

            brief_path = Path(temp_dir) / "launch_brief.md"
            state_path = Path(temp_dir) / "launch_brief_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertTrue(brief_path.is_file())
            self.assertTrue(state_path.is_file())
            self.assertIn("**Baseline brief:**", first)
            self.assertIn("**New since the last brief:** 0.", second)
            self.assertIn(
                "No new pipeline entries since 2026-07-20.",
                second,
            )
            self.assertEqual(len(state["pipeline_ids"]), 1)
            self.assertEqual(state["generated_at"], "2026-07-20T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
