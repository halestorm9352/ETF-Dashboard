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
- User-confirmed Increments 1 through 8.5 are approved and pushed.
- Published Increment 8.5 commit: `6ce3c3f`.
- The local `origin/main` tracking ref still shows `40c100d` because no fetch
  was performed; do not treat that stale ref as the published-state authority.
- Increment 9 is implemented locally for independent review.
- Do not push or deploy Increment 9 until explicitly authorized.

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
- Increment 8: established SEC series/class identity and exact fund-ticker
  mapping enrichment.
- Increment 8.5: classified ETF and mutual-fund vehicles and associated
  mutual-fund classes with their parent series.

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

Placeholder class-only rows carry parent-series context in parser output.
Increment 8.5 reintroduced parent-backed classes as series-scoped events while
continuing to reject orphan class-only standalone identities.

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

## Increment 8.5

### Vehicle Classification

Events and snapshot rows now include `class_name`, `vehicle`, and an internal
`identity_scope`. The user-facing vehicle values are:

- `ETF`
- `Mutual fund share class`
- `Other / unknown`

Classification precedence is:

1. A five-letter ticker ending in `X`, or an explicit class-only/class-suffix
   name, identifies a mutual-fund share class.
2. `ETF` in the series or class name identifies an ETF.
3. Bull/Bear `nX Shares` naming identifies an ETF.
4. An otherwise valid one-to-four-letter ticker identifies an ETF.
5. Rows without a high-confidence signal remain `Other / unknown`.

Classification labels rows; it does not filter mutual-fund-looking rows out of
the result table. Parent-backed class rows retain their class ID, class name,
and ticker in source history, but display the parent series name and use the
parent `(CIK, series_id)` for snapshot identity. Orphan class-only rows remain
excluded, so a class label cannot become a standalone snapshot row. Multiple
class events from one accession remain in source history but count as one
filing occurrence in their parent-series snapshot history. Where more than one
class is available for a series snapshot, the representative preference is ETF,
then mutual-fund share class, then unknown, followed by ticker availability.

### Readiness Changes

Readiness precedence is unchanged except for the two authorized changes:

1. A ticker from the exact SEC fund-ticker mapping is ticker-bearing even when
   the legacy heuristic sanitizer would reject it. A classified mutual-fund
   five-letter `X` ticker is also ticker-bearing. This prevents authoritative
   symbols such as `FLCSX` from displaying `Needs ticker`.
2. `Launch candidate` now additionally requires `vehicle == ETF`. An effective
   mutual-fund share class with initial/amendment history falls through to
   `Effective (amendment)`; an all-485BPOS history remains
   `Effective (485(b) update)`.

Initial review, timing detection, needs-ticker, effective-update/amendment, and
waiting precedence were otherwise left intact. `ticker_at_filing` remains
immutable; raw five-letter class tickers present in an SEC index table are now
preserved as filing values.

### UI And Workbook

- The latest snapshot table and workbook include `class_name` and `vehicle`.
- Copy now describes fund/parent-series snapshot rows rather than ETF-only rows.
- The first summary card is labeled `Snapshot Rows`, and theme copy refers to
  classified fund names.
- Filer/date filters and the filer success/failure coverage caption are
  unchanged because vehicle classification does not alter the search set.
- `DATA_VERSION` was bumped to invalidate pre-classification cached shapes.

### Verification

- Python: fresh 3.14 virtual environment installed from `requirements.txt`.
- Full suite: `Ran 50 tests`.
- Result: `OK (expected failures=1)`.
- `py_compile` passed for all changed active modules.
- Both Increment 8.5 expected failures now pass:
  parent-series display for class-only names, and preservation/classification
  of five-letter mutual-fund class tickers.
- The sole remaining expected failure is S-1/A quoted-prose `IBIT` extraction,
  still assigned to Increment 9. Its parser regex and test were not changed.

New coverage includes classification precedence, ambiguous-row handling,
parent-series snapshot association without source-event loss, authoritative
mapped-ticker readiness, mutual-fund launch-candidate exclusion without table
exclusion, and the two converted fixture cases.

## Increment 9

### Smaller Fixes

1. **IBIT quoted prose:** `extract_ticker()` now recognizes the narrow phrase
   `under the ticker symbol "XXXX."` in the accession-backed iShares Bitcoin
   Trust S-1/A fixture. The exact added regex is
   `\bunder\s+the\s+ticker\s+symbol\s+"([A-Z]{3,4})\.?"`. The final expected
   failure is now a passing fixture test; no other parser regex changed.
2. **Mapping visibility:** `SecFundTickerMapping` carries availability and an
   error summary, and `FilingEventResults.mapping_status` passes that metadata
   through the cached Streamlit loader. The UI captions unavailable mapping
   data as potentially incomplete. Force refresh retries naturally because the
   mapping fetch remains inside the refresh-token-keyed cached function.
3. **Post-enrichment classification:** all rows are reclassified after exact
   and fallback ticker enrichment. An ID-less row enriched to a valid ETF
   ticker can now pass the existing ETF launch-candidate gate. No readiness
   precedence changed, and `ticker_at_filing` remains immutable.
4. **Identity-scope stabilization:** after classification, any class ID that is
   series-scoped in one filing remains series-scoped throughout that class's
   history. Snapshot derivation repeats this normalization on copied rows, so
   callers cannot split one class into class- and series-identity rows while
   source events remain untouched.
5. **Empty snapshots:** readiness enrichment returns a typed empty result with
   all derived columns. The app shows a friendly no-matches message and avoids
   datetime formatting on empty display data.
6. **Timestamp normalization:** timezone-aware `accepted_at` values convert to
   UTC before their timezone is removed; date-only fallbacks remain naive
   midnight and therefore share one naive-UTC comparison basis.
7. **Documentation:** README and this handoff now record the accepted
   dual-vehicle behavior. A series with an ETF class and mutual-fund classes
   intentionally yields two rows: the standalone ETF class and one parent
   series row for the mutual-fund classes.

### Verification

- Fresh Python 3.14 virtual environment installed from `requirements.txt`.
- Full suite: `Ran 56 tests`.
- Result: `OK` with zero expected failures.
- All SEC fixture tests pass after the one sanctioned parser regex addition.
- `py_compile` passed for all active modules and tests.
- `git diff --check` passed.

New regression coverage includes unavailable mapping metadata, post-fallback
ETF readiness, class identity-scope flips, empty readiness dataframes,
same-day UTC timestamp ordering, quoted-prose IBIT extraction, and explicit
dual-vehicle two-row snapshots.

## Unrelated Files

- `README.md` was previously untracked and is intentionally included in
  Increment 9 because documentation alignment is part of the approved scope.
- Ignore `.claude/worktrees/peaceful-bartik-994ff6`.
