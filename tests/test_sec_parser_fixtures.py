import unittest
from pathlib import Path

import sec_filings
import sec_parsers
from config import INDEX_PAGE_MAX_CHARS
from sec_filings import _merge_series_entries_with_pairs
from sec_parsers import (
    EFFECTIVENESS_ANCHOR,
    EFFECTIVENESS_LEGACY_WINDOW_CHARS,
    extract_named_ticker_pairs,
    extract_rule_485_effectiveness,
    extract_series_entries,
    extract_ticker,
)
from vehicle_classifier import MUTUAL_FUND_SHARE_CLASS


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sec"


def load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


class SecParserFixtureTests(unittest.TestCase):
    def test_large_trust_index_cap_preserves_series_identity_table(self):
        text = load_fixture("proshares_485apos_large_index.html")

        entries = extract_series_entries(text[:INDEX_PAGE_MAX_CHARS])

        self.assertEqual(len(entries), 5)
        self.assertTrue(all(entry["series_id"] for entry in entries))
        self.assertTrue(all(entry["class_id"] for entry in entries))

    def test_parser_and_filing_module_contract_versions_match(self):
        self.assertEqual(
            sec_parsers.MODULE_CONTRACT_VERSION,
            sec_filings.MODULE_CONTRACT_VERSION,
        )
        self.assertEqual(sec_parsers.MODULE_CONTRACT_VERSION, 12)

    def test_s1_without_final_ticker_remains_unlisted(self):
        text = load_fixture("ishares_bitcoin_s1_primary.html")

        self.assertEqual(extract_ticker(text), "")

    def test_s1_amendment_extracts_ticker_in_quoted_prose(self):
        text = load_fixture("ishares_bitcoin_s1a_primary.html")

        self.assertEqual(extract_ticker(text), "IBIT")

    def test_s1_amendment_extracts_final_ibit_ticker(self):
        text = load_fixture("ishares_bitcoin_s1a_primary.html")

        self.assertEqual(extract_ticker(text), "IBIT")

    def test_n1a_multi_series_index_preserves_all_blank_ticker_rows(self):
        text = load_fixture("sei_n1a_index.html")

        entries = extract_series_entries(text)

        self.assertEqual(len(entries), 4)
        self.assertEqual(entries[0]["etf_name"], "SEI Large Cap Low Volatility Factor ETF")
        self.assertEqual(entries[0]["series_id"], "S000075036")
        self.assertEqual(entries[0]["class_id"], "C000233738")
        self.assertEqual(entries[-1]["series_id"], "S000075039")
        self.assertTrue(all(entry["ticker"] == "" for entry in entries))

    def test_485apos_multi_fund_index_does_not_promote_underlying_ticker(self):
        text = load_fixture("direxion_485apos_index.html")

        entries = extract_series_entries(text)

        self.assertEqual(len(entries), 3)
        self.assertEqual(extract_named_ticker_pairs(text), [])
        self.assertEqual(extract_ticker(text), "")
        self.assertEqual(
            [entry["etf_name"] for entry in entries[:2]],
            [
                "Direxion Daily PYPL Bull 2X Shares",
                "Direxion Daily PYPL Bear 1X Shares",
            ],
        )
        self.assertEqual(entries[0]["series_id"], "S000092897")
        self.assertEqual(entries[0]["class_id"], "C000260947")
        self.assertEqual(entries[2]["etf_name"], "Direxion Daily RBLX Bull 2X Shares")

    def test_485apos_repeated_ticker_proposals_are_rejected_as_ambiguous(self):
        text = load_fixture("xtrackers_485apos_primary.html")

        pairs = extract_named_ticker_pairs(text)
        entries = [
            {"etf_name": pair["etf_name"], "ticker": ""}
            for pair in pairs
        ]
        merged = _merge_series_entries_with_pairs(entries, pairs)

        self.assertEqual(len(pairs), 3)
        self.assertEqual({pair["ticker"] for pair in pairs}, {"XXXX"})
        self.assertTrue(all(entry["ticker"] == "" for entry in merged))

    def test_485apos_placeholder_classes_display_under_parent_series(self):
        text = load_fixture("american_funds_485apos_index.html")

        entries = extract_series_entries(text)

        self.assertEqual(
            [entry["etf_name"] for entry in entries],
            [
                "Global Small Capitalization Fund",
                "Global Small Capitalization Fund",
                "Global Small Capitalization Fund",
                "Global Small Capitalization Fund",
                "International Fund",
                "International Fund",
                "International Fund",
                "International Fund",
                "International Fund",
                "Managed Risk International Fund",
                "Managed Risk International Fund",
            ],
        )
        self.assertEqual(entries[0]["class_name"], "Class 1")
        self.assertEqual(entries[-1]["class_name"], "Class P2")
        self.assertTrue(
            all(entry["vehicle"] == MUTUAL_FUND_SHARE_CLASS for entry in entries)
        )
        self.assertTrue(all(entry["identity_scope"] == "series" for entry in entries))
        self.assertEqual(entries[0]["series_id"], "S000008790")
        self.assertEqual(entries[0]["series_name"], "Global Small Capitalization Fund")
        self.assertEqual(entries[4]["series_id"], "S000008792")
        self.assertEqual(entries[-1]["series_id"], "S000040666")

    def test_485apos_placeholder_classes_include_parent_series(self):
        text = load_fixture("american_funds_485apos_index.html")

        entries = extract_series_entries(text)

        self.assertTrue(all(entry["etf_name"] == entry["series_name"] for entry in entries))
        self.assertTrue(all(entry["class_name"].startswith("Class ") for entry in entries))

    def test_485bpos_mutual_fund_classes_keep_five_letter_tickers(self):
        text = load_fixture("fidelity_485bpos_index.html")

        entries = extract_series_entries(text)

        self.assertEqual(len(entries), 13)
        self.assertEqual(entries[1]["etf_name"], "Fidelity Large Cap Stock Fund")
        self.assertEqual(
            entries[1]["class_name"],
            "Fidelity Advisor Large Cap Stock Fund: Class C",
        )
        self.assertEqual(entries[0]["series_id"], "S000055364")
        self.assertEqual(entries[0]["class_id"], "C000174182")
        self.assertEqual(entries[5]["class_id"], "C000259433")
        self.assertEqual(entries[5]["ticker"], "FLAFX")
        self.assertEqual(entries[6]["series_id"], "S000055365")
        self.assertEqual(entries[7]["class_id"], "C000174184")
        self.assertEqual(
            [entry["ticker"] for entry in entries],
            [
                "FLCSX",
                "FLAJX",
                "FLAHX",
                "FHZTX",
                "FLAZX",
                "FLAFX",
                "FMCSX",
                "FKMCX",
                "FMCNX",
                "FMCWX",
                "FMCHX",
                "FMCJX",
                "FMCQX",
            ],
        )
        self.assertTrue(
            all(entry["vehicle"] == MUTUAL_FUND_SHARE_CLASS for entry in entries)
        )

    def test_tags_intact_edgar_table_preserves_real_cell_offsets(self):
        text = load_fixture("fidelity_485bpos_index.html")

        entries = extract_series_entries(text)

        self.assertIn('<td class="seriesName" scope="row">', text)
        self.assertEqual(
            (
                entries[5]["series_id"],
                entries[5]["class_id"],
                entries[5]["class_name"],
            ),
            (
                "S000055364",
                "C000259433",
                "Fidelity Advisor Large Cap Stock Fund: Class A",
            ),
        )

    def test_485bpos_mutual_fund_class_tickers_are_classification_evidence(self):
        text = load_fixture("fidelity_485bpos_index.html")

        entries = extract_series_entries(text)

        self.assertEqual(entries[0]["ticker"], "FLCSX")
        self.assertEqual(entries[1]["ticker"], "FLAJX")

    def test_485bpos_cover_detects_immediate_effectiveness(self):
        text = load_fixture("etf_opportunities_485bpos_primary.html")

        result = extract_rule_485_effectiveness(text)

        self.assertEqual(
            result,
            {
                "effectiveness_basis": "rule_485_b_immediate",
                "effectiveness_days": 0,
                "designated_effective_date": "",
                "effectiveness_label": "Immediately upon filing (Rule 485(b))",
            },
        )

    def test_485bpos_anchor_beyond_legacy_window_detects_immediate_effectiveness(self):
        excerpt = load_fixture("defiance_485bpos_beyond_window_primary.html")
        text = "P" * (EFFECTIVENESS_LEGACY_WINDOW_CHARS + 3_500) + excerpt

        self.assertGreater(
            text.lower().find(EFFECTIVENESS_ANCHOR),
            EFFECTIVENESS_LEGACY_WINDOW_CHARS,
        )
        self.assertEqual(
            extract_rule_485_effectiveness(text),
            {
                "effectiveness_basis": "rule_485_b_immediate",
                "effectiveness_days": 0,
                "designated_effective_date": "",
                "effectiveness_label": "Immediately upon filing (Rule 485(b))",
            },
        )

    def test_485bpos_checked_designated_date_fixture(self):
        text = load_fixture("etf_opportunities_485bpos_designated_primary.html")

        self.assertEqual(
            extract_rule_485_effectiveness(text),
            {
                "effectiveness_basis": "rule_485_b_designated_date",
                "effectiveness_days": None,
                "designated_effective_date": "June 30, 2026",
                "effectiveness_label": (
                    "Designated date June 30, 2026 (Rule 485(b))"
                ),
            },
        )

    def test_485bpos_direct_designated_date_fixture(self):
        text = load_fixture("fidelity_485bpos_direct_designated_primary.html")

        self.assertEqual(
            extract_rule_485_effectiveness(text),
            {
                "effectiveness_basis": "rule_485_b_designated_date",
                "effectiveness_days": None,
                "designated_effective_date": "July 25, 2025",
                "effectiveness_label": (
                    "Designated date July 25, 2025 (Rule 485(b))"
                ),
            },
        )

    def test_485bpos_rule_then_paragraph_designated_date_fixture(self):
        text = load_fixture("dimensional_485bpos_rule_paragraph_designated_primary.html")

        self.assertEqual(
            extract_rule_485_effectiveness(text),
            {
                "effectiveness_basis": "rule_485_b_designated_date",
                "effectiveness_days": None,
                "designated_effective_date": "April 30, 2026",
                "effectiveness_label": (
                    "Designated date April 30, 2026 (Rule 485(b))"
                ),
            },
        )

    def test_inline_checked_marker_does_not_leak_to_unchecked_later_options(self):
        text = """
        It is proposed that this filing will become effective:
        \u2611 immediately upon filing pursuant to paragraph (b)
        \u2610 60 days after filing pursuant to paragraph (a)(1)
        \u2610 75 days after filing pursuant to paragraph (a)(2)
        """

        result = extract_rule_485_effectiveness(text)

        self.assertEqual(result["effectiveness_basis"], "rule_485_b_immediate")
        self.assertEqual(result["effectiveness_days"], 0)

    def test_wingdings_markers_select_parenthesized_designated_date(self):
        text = """
        It is proposed that this filing will become effective:
        q immediately upon filing pursuant to paragraph (b)
        \u00fe on (August 17, 2025) pursuant to paragraph (b)
        q 60 days after filing pursuant to paragraph (a)(1)
        """

        self.assertEqual(
            extract_rule_485_effectiveness(text),
            {
                "effectiveness_basis": "rule_485_b_designated_date",
                "effectiveness_days": None,
                "designated_effective_date": "August 17, 2025",
                "effectiveness_label": (
                    "Designated date August 17, 2025 (Rule 485(b))"
                ),
            },
        )


if __name__ == "__main__":
    unittest.main()
