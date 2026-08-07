from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from readiness import INITIAL_REVIEW, UPCOMING_LAUNCH
from scripts.generate_launch_brief import build_brief_data, generate_brief
from sec_parsers import PARSER_VERSION
from store import open_store, upsert_events
from tests.test_store import sample_event


def brief_row(**overrides):
    row = {
        "etf_name": "Example Future ETF",
        "filer": "Example Trust",
        "theme": "Thematic Equity",
        "launch_readiness": UPCOMING_LAUNCH,
    }
    row.update(overrides)
    return row


class LaunchBriefTests(unittest.TestCase):
    TODAY = date(2026, 8, 7)

    def test_build_brief_data_has_pipeline_totals_and_ranked_counts(self):
        rows = [
            brief_row(),
            brief_row(etf_name="Second ETF"),
            brief_row(
                etf_name="Initial ETF",
                filer="Another Trust",
                theme="Fixed Income / Credit",
                launch_readiness=INITIAL_REVIEW,
            ),
        ]

        brief = build_brief_data(rows, self.TODAY)

        self.assertEqual(brief["as_of"], "2026-08-07")
        self.assertEqual(brief["total"], 3)
        self.assertEqual(brief["upcoming"], 2)
        self.assertEqual(brief["initial_review"], 1)
        self.assertEqual(
            brief["top_filers"],
            [
                {"name": "Example Trust", "count": 2},
                {"name": "Another Trust", "count": 1},
            ],
        )
        self.assertEqual(
            brief["top_themes"],
            [
                {"name": "Thematic Equity", "count": 2},
                {"name": "Fixed Income / Credit", "count": 1},
            ],
        )

    def test_rankings_are_stable_and_limited_to_eight(self):
        rows = [
            brief_row(filer=f"Trust {index:02d}", theme=f"Theme {index:02d}")
            for index in range(10)
        ]

        brief = build_brief_data(rows, self.TODAY)

        self.assertEqual(
            [item["name"] for item in brief["top_filers"]],
            [f"Trust {index:02d}" for index in range(8)],
        )
        self.assertEqual(len(brief["top_themes"]), 8)

    def test_structured_output_is_deterministic_and_has_no_delta_content(self):
        rows = [brief_row(), brief_row(filer="Another Trust")]

        first = build_brief_data(rows, self.TODAY)
        second = build_brief_data(list(reversed(rows)), self.TODAY)
        serialized = json.dumps(first, sort_keys=True)

        self.assertEqual(first, second)
        self.assertNotIn("New This Period", serialized)
        self.assertNotIn("delta", serialized.casefold())
        self.assertNotIn("pipeline_ids", serialized)

    def test_empty_pipeline_produces_zeroed_summary(self):
        brief = build_brief_data([], self.TODAY)

        self.assertEqual(brief["total"], 0)
        self.assertEqual(brief["upcoming"], 0)
        self.assertEqual(brief["initial_review"], 0)
        self.assertEqual(brief["top_filers"], [])
        self.assertEqual(brief["top_themes"], [])

    def test_generate_brief_writes_single_structured_artifact(self):
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

            with patch("scripts.generate_launch_brief.CIKS", ["0000000001"]):
                first = generate_brief(store_path, date(2026, 7, 20))
                second = generate_brief(store_path, date(2026, 7, 20))

            brief_path = Path(temp_dir) / "launch_brief.json"
            saved = json.loads(brief_path.read_text(encoding="utf-8"))

            self.assertTrue(brief_path.is_file())
            self.assertFalse((Path(temp_dir) / "launch_brief.md").exists())
            self.assertFalse((Path(temp_dir) / "launch_brief_state.json").exists())
            self.assertEqual(first, second)
            self.assertEqual(saved, first)
            self.assertEqual(saved["as_of"], "2026-07-20")
            self.assertEqual(saved["total"], 1)


if __name__ == "__main__":
    unittest.main()
