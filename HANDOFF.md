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
- User-confirmed Increments 1 through 10 are approved and pushed.
- Increment 9 commit: `1ac2782`.
- Published Increment 10 commit: `60214c2`.
- Increment 11 is implemented locally for independent review and is not pushed.

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

## Increment 10

### Final Cleanup

1. Removed the dead news ticker, embedded component script, and all
   `.etf-ticker-*` / `.etf-news-*` CSS. The unused components import was
   removed; `escape` remains because live theme-card HTML still uses it.
2. Renamed the first summary card to `Funds Loaded`.
3. Added a process-wide SEC interval lock targeting eight requests per second
   across worker threads. SEC 403/429 responses retry with backoff, honor
   numeric or HTTP-date `Retry-After` with a 30-second maximum delay, and raise
   after the final attempt.
   Submission, index, supporting, and prefetched primary-document failures
   therefore reach the existing per-CIK failed status path.
4. Widened only `sanitize_ticker()` from `[A-Z]{3,4}` to `[A-Z]{2,5}` and used
   it for structured series-table cells. Free-text extraction regexes were not
   widened, and `INVALID_TICKERS` still applies.
5. Removed the tracked `.claude` gitlink from the index and added `.claude/` to
   `.gitignore`; local Claude files were not deleted.
6. Cached fetch timestamps are now timezone-aware UTC values and display in
   `America/New_York` with an explicit `ET` label. Legacy naive cached values
   are interpreted as UTC during the 30-minute transition window.
7. Bumped `DATA_VERSION` so cached rows are rebuilt under the wider structured
   ticker validation.

### Verification

- Fresh Python 3.14 environment installed from `requirements.txt`.
- Full suite: `Ran 62 tests`.
- Result: `OK` with zero expected failures.
- `py_compile` passed for all active modules and tests.
- `git diff --check` passed.
- New tests cover shared 125 ms SEC spacing, the 30-second `Retry-After` cap,
  terminal 403 propagation, per-CIK rate-limit failure status,
  two-to-five-letter ticker sanitization, and five-letter structured
  series-table tickers.
- A normal live SEC search was not benchmarked during this increment, so no
  before/after slowdown was observed or claimed. The configured target remains
  eight requests per second as approved.

## Increment 11

### Large-Trust Series Identity

1. Raised only `INDEX_PAGE_MAX_CHARS` from 60,000 to 300,000 so large EDGAR
   filing-index pages retain their late series/class tables.
2. Added the verbatim 107,838-character ProShares 485APOS index page for
   accession `0001174610-26-000432`. Its first `contractRow` begins after
   character 100,000, and the fixture test truncates with the production
   constant before asserting all five series and class IDs.
3. Extended the shared class-only pattern to accept repeated hyphen segments,
   including `Class 529-F-1` and `Class 529-F-1 Shares`, while retaining the
   negative `Class Act Growth ETF` case. The filing placeholder helper delegates
   to this shared classifier, so filtering and vehicle classification remain
   aligned.
4. Added `MODULE_CONTRACT_VERSION = 11` to `sec_parsers.py` and
   `sec_filings.py`. `app.py` now expects version 11, reloads a mismatched module
   once, and visibly stops with a reboot message if the mismatch remains.
   Removed the obsolete config import fallback and its duplicated constants.
5. Bumped `DATA_VERSION` to the Increment 11 v7 value.

### Verification

- Fresh Python 3.14 virtual environment installed from `requirements.txt`.
- Full suite: `Ran 65 tests in 0.623s`; result `OK` with zero expected failures.
- `py_compile` passed for all active modules and tests.
- Live production-path spot-check fetched the cited ProShares page through
  `extract_text(..., INDEX_PAGE_MAX_CHARS)` and parsed five entries. All five
  carried non-empty `series_id` and `class_id` values.
- Increment 12 has not started. Do not push Increment 11 until review approval.

## Local-Only Files

- `.claude/` remains available locally but is ignored and untracked.
- Watch item only: structured series-table tickers pass through
  `INVALID_TICKERS`, which could reject a legitimate ticker that collides with
  a denylisted word such as `MID`. Do not change this without a future approved
  increment.
