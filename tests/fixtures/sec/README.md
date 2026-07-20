# SEC Parser Fixture Provenance

These fixtures are trimmed excerpts of public SEC EDGAR filings. They retain
the table rows, cover-page labels, and nearby text used by `sec_parsers.py`
while omitting unrelated prospectus content.

| Fixture | Form | Filed | Accession | Source | Purpose |
| --- | --- | --- | --- | --- | --- |
| `ishares_bitcoin_s1_primary.html` | S-1 | 2023-06-15 | 0001437749-23-017574 | https://www.sec.gov/Archives/edgar/data/1980994/000143774923017574/bit20230608_s1.htm | Initial commodity-trust registration with no final ticker. |
| `ishares_bitcoin_s1a_primary.html` | S-1/A | 2024-01-09 | 0001437749-24-001043 | https://www.sec.gov/Archives/edgar/data/1980994/000143774924001043/bit20240109_s1a.htm | Amendment that names the final IBIT ticker in prose. |
| `sei_n1a_index.html` | N-1A | 2021-10-29 | 0001104659-21-131875 | https://www.sec.gov/Archives/edgar/data/1888997/000110465921131875/0001104659-21-131875-index.htm | Initial multi-series filing with blank ticker cells. |
| `direxion_485apos_index.html` | 485APOS | 2025-03-14 | 0001193125-25-054770 | https://www.sec.gov/Archives/edgar/data/1424958/000119312525054770/0001193125-25-054770-index.htm | Multi-fund filing whose fund names refer to the same underlying PYPL ticker. |
| `xtrackers_485apos_primary.html` | 485APOS | 2023-03-13 | 0001213900-23-019123 | https://www.sec.gov/Archives/edgar/data/1503123/000121390023019123/ea151168_485apos.htm | Multi-fund proposal table that repeats the placeholder ticker XXXX. |
| `american_funds_485apos_index.html` | 485APOS | 2026-03-02 | 0000051931-26-000302 | https://www.sec.gov/Archives/edgar/data/729528/000005193126000302/0000051931-26-000302-index.htm | Placeholder class-only identities from a mutual-fund series filing. |
| `fidelity_485bpos_index.html` | 485BPOS | 2026-06-24 | 0000819118-26-000136 | https://www.sec.gov/Archives/edgar/data/819118/000081911826000136/0000819118-26-000136-index.htm | Tags-intact EDGAR table excerpt with parent series, mutual-fund-style share classes, and five-letter tickers. |
| `proshares_485apos_large_index.html` | 485APOS | 2026-07-17 | 0001174610-26-000432 | https://www.sec.gov/Archives/edgar/data/1174610/000117461026000432/0001174610-26-000432-index.htm | Full large-trust index page whose series/class table begins after character 100,000, guarding the production index truncation cap. |
| `etf_opportunities_485bpos_primary.html` | 485BPOS | 2026-07-17 | 0001771146-26-001459 | https://www.sec.gov/Archives/edgar/data/1771146/000177114626001459/ck0001771146-20260717.htm | Checked Rule 485(b) immediate-effectiveness cover option. |
