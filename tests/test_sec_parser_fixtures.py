import unittest
from pathlib import Path

from sec_filings import _merge_series_entries_with_pairs
from sec_parsers import (
    extract_named_ticker_pairs,
    extract_rule_485_effectiveness,
    extract_series_entries,
    extract_ticker,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sec"


def load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


class SecParserFixtureTests(unittest.TestCase):
    def test_s1_without_final_ticker_remains_unlisted(self):
        text = load_fixture("ishares_bitcoin_s1_primary.html")

        self.assertEqual(extract_ticker(text), "")

    def test_s1_amendment_currently_misses_ticker_in_quoted_prose(self):
        text = load_fixture("ishares_bitcoin_s1a_primary.html")

        self.assertEqual(extract_ticker(text), "")

    # Increment 9's post-fixture parser follow-up handles quoted S-1 tickers;
    # Increment 8's mutual-fund series/class map does not cover commodity trusts.
    @unittest.expectedFailure
    def test_s1_amendment_eventually_extracts_final_ibit_ticker(self):
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

    def test_485apos_placeholder_classes_are_current_parser_identities(self):
        text = load_fixture("american_funds_485apos_index.html")

        entries = extract_series_entries(text)

        self.assertEqual(
            [entry["etf_name"] for entry in entries],
            [
                "Class 1",
                "Class 2",
                "Class 4",
                "Class 1A",
                "Class 1",
                "Class 2",
                "Class 3",
                "Class 4",
                "Class 1A",
                "Class P1",
                "Class P2",
            ],
        )
        self.assertEqual(entries[0]["series_id"], "S000008790")
        self.assertEqual(entries[0]["series_name"], "Global Small Capitalization Fund")
        self.assertEqual(entries[4]["series_id"], "S000008792")
        self.assertEqual(entries[-1]["series_id"], "S000040666")

    # Increment 8.5 associates classes with their parent series and prevents
    # class-only names from becoming standalone snapshot identities.
    @unittest.expectedFailure
    def test_485apos_placeholder_classes_eventually_include_parent_series(self):
        text = load_fixture("american_funds_485apos_index.html")

        entries = extract_series_entries(text)

        self.assertTrue(all(not entry["etf_name"].startswith("Class ") for entry in entries))

    def test_485bpos_mutual_fund_classes_currently_drop_five_letter_tickers(self):
        text = load_fixture("fidelity_485bpos_index.html")

        entries = extract_series_entries(text)

        self.assertEqual(len(entries), 13)
        self.assertEqual(entries[1]["etf_name"], "Fidelity Advisor Large Cap Stock Fund: Class C")
        self.assertEqual(entries[0]["series_id"], "S000055364")
        self.assertEqual(entries[0]["class_id"], "C000174182")
        self.assertEqual(entries[5]["class_id"], "C000259433")
        self.assertEqual(entries[5]["ticker"], "")
        self.assertEqual(entries[6]["series_id"], "S000055365")
        self.assertEqual(entries[7]["class_id"], "C000174184")
        self.assertTrue(all(entry["ticker"] == "" for entry in entries))

    def test_tags_intact_edgar_table_preserves_real_cell_offsets(self):
        text = load_fixture("fidelity_485bpos_index.html")

        entries = extract_series_entries(text)

        self.assertIn('<td class="seriesName" scope="row">', text)
        self.assertEqual(
            (entries[5]["series_id"], entries[5]["class_id"], entries[5]["etf_name"]),
            (
                "S000055364",
                "C000259433",
                "Fidelity Advisor Large Cap Stock Fund: Class A",
            ),
        )

    # Increment 8.5 captures class-level C-numbers and five-letter mutual-fund
    # tickers as evidence for vehicle classification.
    @unittest.expectedFailure
    def test_485bpos_mutual_fund_classes_eventually_keep_five_letter_tickers(self):
        text = load_fixture("fidelity_485bpos_index.html")

        entries = extract_series_entries(text)

        self.assertEqual(entries[0]["ticker"], "FLCSX")
        self.assertEqual(entries[1]["ticker"], "FLAJX")

    def test_485bpos_cover_detects_immediate_effectiveness(self):
        text = load_fixture("etf_opportunities_485bpos_primary.html")

        result = extract_rule_485_effectiveness(text)

        self.assertEqual(result["effectiveness_basis"], "rule_485_b_immediate")
        self.assertEqual(result["effectiveness_days"], 0)


if __name__ == "__main__":
    unittest.main()
