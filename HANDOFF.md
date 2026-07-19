# ETF Dashboard Handoff

Last updated: 2026-07-19

## Workflow

- Claude reviews and approves each increment.
- Codex implements exactly one increment per commit.
- Run `python -m unittest discover -s tests -v` after every change.
- Do not push an increment until the user explicitly authorizes it.
- Preserve filing events as source history and present one latest,
  amendment-aware snapshot row per fund.

## Git State

- Branch: `sync-main`.
- User-confirmed published Increment 7 commit: `970380d`.
- The local `origin/main` tracking ref still shows `40c100d` because no fetch
  was performed during Increment 8; do not treat that stale ref as permission
  to push.
- Increment 8 is implemented locally for independent review.
- Do not push or deploy Increment 8 until explicitly authorized.

## Completed Increments

- Increment 1: corrected cache semantics, added Force refresh, and displayed
  the cached fetch timestamp.
- Increment 2: deleted the obsolete launch-snapshot workflow.
- Increment 3: bounded runtime dependencies and pinned Python 3.14.
- Increment 4: capped later-filing ticker enrichment at 90 days.
- Increment 5: added per-filer partial-failure reporting.
- Increment 5.5: tightened ticker, placeholder-name, and theme data hygiene.
- Increment 6: gated launch candidates by filing history.
- Increment 7: added accession-sourced parser fixtures and baseline tests.

## Increment 8

### Fixture Corrections

All reconstructed index fixtures were checked against their cited EDGAR
accessions before identity code changed.

Fidelity accession `0000819118-26-000136`:

- FLCSX: fabricated `C000023921` -> real `C000174182`.
- Advisor Class C through Z: fabricated `C000267001-C000267004` -> real
  `C000259429-C000259432`.
- Restored omitted Advisor Class A: `C000259433`, ticker `FLAFX`.
- FMCSX: fabricated `C000023922` -> real `C000174183`.
- Class K / FKMCX: fabricated `C000101234` -> real `C000174184`.
- Added parent series `S000055364` and `S000055365`.
- Replaced the minimal reconstruction with a tags-intact EDGAR table excerpt
  to verify genuine `seriesCell` and contract-cell offsets.

Other index fixtures:

- SEI class IDs `C000233738-C000233741` were correct; added parent series
  `S000075036-S000075039`.
- Direxion class IDs `C000260947-C000260949` were correct; added parent series
  `S000092897-S000092899` and corrected class `C000260949` from the fabricated
  RDDT name to the filed RBLX name.
- American Funds retained its verified class IDs, restored five omitted class
  rows, and added parent series `S000008790`, `S000008792`, and `S000040666`.

### Identity Model

Filing events now carry:

- `series_id`
- `series_name`
- `class_id`

Snapshot and history identity precedence is:

1. Exact `(CIK, series_id, class_id)`.
2. `(CIK, series_id)` when no class ID exists.
3. `(CIK, normalized fund name)` only when SEC IDs are absent.

A name-only historical event is bridged to a unique later SEC identity when
the same CIK and normalized name map unambiguously. This prevents duplicate
snapshot rows while preserving the complete event list. Event IDs use the
class ID, then series ID, then normalized name as their accession-local token.

Placeholder class-only rows now carry parent-series context in parser output,
but remain excluded from standalone events. Increment 8.5 will decide how to
reintroduce relevant classes in a vehicle-aware series view.

### Ticker Enrichment

- Fetches `https://www.sec.gov/files/company_tickers_mf.json` once per cached
  search execution.
- Parses the documented `cik`, `seriesId`, `classId`, and `symbol` fields.
- Joins on exact normalized CIK + series ID + class ID immediately after the
  index table is parsed.
- Preserves `ticker_at_filing`; mapped values update only current `ticker` and
  set `ticker_source = sec_fund_ticker_map`.
- Identified rows never use name-based later-filing ticker inference.
- The existing later-filing heuristic remains only for rows without SEC IDs.
- Heuristic tickers still pass through `sanitize_ticker` and `INVALID_TICKERS`.
  Only exact SEC-map symbols bypass that denylist, because the authoritative
  ID join makes heuristic false-positive protection redundant for those rows.
- The data version was bumped so old cached event shapes are not reused.
- The latest-snapshot workbook now includes `series_id` and `class_id`.

### Verification

- Python: 3.14.3 isolated virtual environment.
- Full suite: `Ran 43 tests in 0.165s`.
- Result: `OK (expected failures=3)`.
- `py_compile` passed for all active modules and tests.
- `git diff --check` passed.
- Readiness precedence and cache-key structure were not changed.

New coverage includes:

- SEC mapping field-order parsing.
- End-to-end parsed-ID-to-mapping enrichment.
- Exact identity join and immutable `ticker_at_filing`.
- Five-letter official symbol display normalization.
- Name-based fallback only when IDs are absent.
- Identified rows refusing later-filing heuristic enrichment.
- Snapshot continuity across a fund rename with stable IDs.
- Name-only history bridging to a unique SEC identity without duplicates.
- Genuine EDGAR table cell offsets and corrected fixture relationships.

## Expected Failures

All three Increment 7 expected failures remain deliberate:

- S-1/A quoted-prose `IBIT` extraction remains assigned to Increment 9.
- Placeholder class rows still appear as class names in raw parser output;
  Increment 8 now supplies parent context, while Increment 8.5 will implement
  vehicle-aware display and reintroduction.
- Raw heuristic parsing still rejects five-letter mutual-fund tickers;
  Increment 8 enriches them at the event layer through exact SEC IDs, while
  Increment 8.5 will use class tickers for vehicle classification.

## Increment 8.5 Notes

- Do not exclude mutual-fund-looking rows generally.
- Add vehicle classification and conversion-candidate detection.
- Use the series/class relationships added in Increment 8.
- Reintroduce relevant ETF classes keyed appropriately to their parent series.
- Stop and ask if required index pages do not contain class-level ticker data.

## Unrelated Files

- `README.md` remains untracked and was not modified.
- Ignore `.claude/worktrees/peaceful-bartik-994ff6`.
