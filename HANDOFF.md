# ETF Dashboard Handoff

Last updated: 2026-08-07

## Workflow

- Claude reviews and approves each increment.
- Codex implements exactly one increment per commit.
- Run `python -m unittest discover -s tests -v` after every change.
- Do not push an increment until the user explicitly authorizes it.
- Preserve filing events as source history and present one latest,
  amendment-aware snapshot row per fund.

## Git State

- Branch: `sync-main`.
- Increments 1 through 24 are approved, pushed, and published.
- Local `HEAD` and `origin/main` both resolve to Increment 24 commit `6859563`
  before Increment 25.
- The scheduled ingest may add store-only bot commits independently. Always
  fetch and fast-forward before starting an approved increment.
- Increment 25 is documentation-only and must stop for independent review
  before push.

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
- Increment 9: resolved the final parser fixture and accumulated data-path
  correctness fixes.
- Increment 10: removed dead UI, added the shared SEC limiter, and completed
  low-risk cleanup.
- Increment 11: preserved large-trust series identity, expanded multi-hyphen
  placeholder handling, and enforced module contract versions.
- Increment 12: scoped the default pipeline to genuinely new funds using
  persistent-ready series age and prior-effectiveness evidence.
- Increments 13a-13c: added the persistent SQLite store, scheduled incremental
  ingest, and store-first app reads with a live tail and offline grace.
- Increment 14: replaced the launch-candidate label with a timing-first,
  eight-state readiness taxonomy and an orthogonal ticker flag.
- Increment 15: recovered Rule 485 effectiveness elections beyond the legacy
  120,000-character cover window.
- Increment 16: introduced parser-version-aware reprocessing and a one-million-
  character primary-document fetch cap.
- Increment 16c: added targeted `--backfill --days N` reprocessing.
- Increment 17: bounded fund identity extraction to prospectus front matter
  while preserving the deeper effectiveness scan.
- Increment 18: limited the default view to not-yet-effective funds.
- Increment 19: added conservative exchange-listing evidence for tickerless ETF
  vehicle classification and preserved authoritative stored vehicles.
- Increment 19b: applied the new vehicle classifier to the recent store window.
- Increment 20: added the ETF share-class competitive-signal watch.
- Increment 21: refreshed the README around the current product and architecture.
- Increment 22: removed retired third-party scraper/news code and stale audits.
- Increment 23: added the deterministic launch-pipeline brief generator.
- Increment 24: published the brief through scheduled ingest and a read-only app
  panel.

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
- Increment 11 was independently approved and pushed as `f39e650`.

## Increment 12

### New-Fund Scoping

1. Added `SERIES_NEW_MONTHS = 18`. Snapshot rows in the specified pipeline
   states use their SEC series registration date to distinguish new-fund work
   from amendments to established series. A series first filed more than 18
   months before the search start becomes `Existing fund amendment`.
2. Added paginated browse-edgar Atom retrieval using the series identifier in
   the supported `CIK=S000...` form. The lookup follows SEC `next` links,
   returns the earliest filing date and a structured status, and uses the
   shared SEC HTTP limiter. Repeated pages, malformed responses, exhaustion,
   and empty histories fail closed rather than supplying partial age evidence.
3. Added an indefinite per-series Streamlit cache keyed by `DATA_VERSION`, the
   force-refresh token, and series ID. Identical searches reuse immutable ages;
   Force refresh retries failures. Failed lookups retain filing-window
   readiness and produce a visible warning plus a failure count.
4. Added an `Include existing-fund amendments` checkbox. The default cards,
   theme counts, workbook, and table exclude `Existing fund amendment` rows.
   Coverage text reports the hidden-row and failed-age-lookup counts.

### Mapping-Gated Prospectus Identity

Large filings can have an index series table unrelated to additional funds in
the primary prospectus. Primary-document name/ticker pairs now survive beside
such a table only when the SEC fund-ticker mapping contains that ticker for the
same CIK. If the mapping is unavailable or the ticker is absent, the pair is
dropped.

- A ticker mapping to exactly one class for that CIK adopts the mapped
  `series_id` and `class_id`.
- An ambiguous same-CIK ticker remains name-scoped and never adopts an
  arbitrary identity.
- Variants sharing one mapped identity collapse before event construction.
  Names without an exchange prefix (`BZX`, `NYSE`, `NASDAQ`, `CBOE`, `ARCA`)
  win over prefixed variants. Snapshot sorting has the same clean-name
  tie-breaker.
- `ticker_at_filing` remains the ticker actually present in the prospectus.

### Prior Effectiveness

Snapshot derivation now records whether the resolved identity has an earlier
`485BPOS` whose detected effective date passed by the latest row's filing date.
For pipeline-state rows, that evidence forces `Existing fund amendment`
regardless of series age. The 18-month rule remains the fallback where no prior
effective filing exists. This handles young but already-live funds such as
BUYB without changing general readiness precedence.

Designated effective dates are parsed in the formats emitted by the SEC parser:
`Month D, YYYY`, `M/D/YYYY`, and ISO `YYYY-MM-DD`. Unparseable values remain
conservative and do not count as prior-effectiveness evidence.

### Versions And Tests

- `DATA_VERSION`: `2026-07-20-increment-12-new-fund-scope-v8`.
- `MODULE_CONTRACT_VERSION`: 12 in `app.py`, `sec_filings.py`, and
  `sec_parsers.py`.
- Full Python 3.14 suite: `Ran 79 tests in 0.456s`; result `OK` with zero
  expected failures.
- `py_compile` passed for all active modules and tests.
- `git diff --check` passed.
- New coverage includes paginated age parsing, failed lookup statuses and
  fallbacks, old/young/missing-ID cases, mapping-gated pair retention and
  rejection beside unrelated index tables, ambiguous ticker identity,
  clean-name preference, prior-effective history derivation, and the young
  series override.

### Live ProShares Acceptance

The production path was run for ProShares CIK `0001174610`, May 1 through July
20. It returned 137 events, 136 snapshot rows, 136 series-age lookups, zero age
failures, and 75 default-hidden existing-amendment rows.

Timings:

- Filing retrieval and parsing: 196.194 seconds.
- Uncached paginated series-age lookups: 369.487 seconds.
- Total: 565.873 seconds. Subsequent app searches reuse the per-series cache.

All required funds appeared exactly once, used clean non-`BZX` names, carried
mapped identity, and were hidden from the default view:

- ANEW: `S000069834` / `C000222595`, `Existing fund amendment`.
- BUYB: `S000104157` / `C000274756`, history `485BPOS -> 485APOS`, prior
  effectiveness true, `Existing fund amendment`.
- EMDV: `S000046274` / `C000144591`, `Existing fund amendment`.
- EUDV: `S000046275` / `C000144592`, `Existing fund amendment`.
- HDG: `S000031041` / `C000096244`, `Existing fund amendment`.
- TMDV: `S000066433` / `C000214312`, `Existing fund amendment`.
- VERS: `S000075552` / `C000234747`, `Existing fund amendment`.

Increment 12 received independent approval after the designated-effective-date
correction. The corrected commit is authorized for push.

## Phase 2 Gameplan (decided with the user, 2026-07-20)

All eleven open product questions were answered by the user. These decisions
are FIXED - do not re-litigate them during implementation:

1. Store = SQLite file committed to the repo by a scheduled GitHub Actions
   ingest workflow. Portability concern acknowledged: mitigate by keeping all
   store access in a UI-agnostic data-layer module (no Streamlit imports) with
   a documented schema, so a future non-Streamlit UI consumes the same file.
2. SQLite, not Parquet.
3. No raw document archiving. Parsed events + accession numbers +
   parser-version stamps are the breadcrumbs; re-fetch from EDGAR on demand.
4. Backfill floor: trailing 12 months (user cut from the proposed 18).
5. Filer universe: existing CIK registry, user-maintained. No auto-widening.
6. Date picker stays current-calendar-year. Do NOT unlock prior years.
7. Ingest cadence: ~7:00 AM and ~4:00 PM Eastern daily.
8. GitHub workflow-failure notifications: enable (user-side setting; the
   workflow itself needs no custom alerting).
9. The Excel workbook remains a crucial deliverable. The UI stays simple -
   the user's prior news rail and AUM tracker crowded the tool and were
   removed. Do not re-crowd it.
10. News is on hold indefinitely.
11. Issuer net flows are the wanted future vector, but only from primary
    sources (N-PORT-class filing data), never scraped websites. Nice-to-have,
    not a commitment. A future full UI port away from Streamlit is a
    long-term possibility - another reason for the UI-agnostic data layer.

Planned increment sequence: 13a (schema + store module + ingest script with
backfill and incremental modes, no app changes) -> 13b (scheduled workflow +
initial store commit) -> 13c (app reads store with live top-up; series ages
served from the store). Each increment: one commit, full suite green, stop
for Claude's independent review before push - unchanged workflow.

## Increment 13a

### Persistent Store

1. Added `store.py`, a standard-library-only SQLite data layer with no direct
   or transitive Streamlit dependency. `SCHEMA_VERSION = 1`; `open_store()`
   creates absent tables and rejects mismatched schema metadata clearly.
2. Added source-event storage with contract-v12 columns and indexes on
   `(cik, date)`, `series_id`, and `accession_number`. Snapshot-derived fields
   remain read-time values and are not persisted.
3. Added accession processing, immutable series registration, and ingest-run
   audit tables. `load_events()` returns source dicts that can pass through the
   existing enrichment and snapshot functions unchanged.
4. Preserved optional `effectiveness_days` values exactly as `None`, empty
   string, or integer. The live equality check caught the initial `None` to
   empty-string coercion; it was corrected and fixture-tested rather than
   papered over.

### Ingest Runner

1. Added `scripts/ingest_filings.py` with `--backfill` and `--incremental`.
   Backfill covers trailing 365 days. Incremental starts three days before the
   last successful end bound.
2. Reuses `_fetch_filings_for_cik` and parse-time SEC mapping enrichment. It
   does not apply later-filing ticker enrichment during ingest; that remains a
   read-time operation.
3. Skips processed accessions, resolves only missing series ages, records
   partial failures, exits nonzero only when every CIK fails, emits progress,
   and ends with `VACUUM`.
4. CIK and series work use at most `SEC_MAX_WORKERS` threads. All network calls
   remain behind the shared process-wide SEC eight-requests-per-second limiter;
   SQLite writes remain serialized on the ingest thread.
5. `data/*.sqlite` is ignored with an explicit note that Increment 13b will
   deliberately un-ignore the initial store.

### Tests And Acceptance

- Added 12 tests across `tests/test_store.py` and
  `tests/test_ingest_filings.py`: event/accession idempotency, exact field
  round trips and filters, pipeline transparency, schema mismatch, Streamlit
  portability, three-day overlap, processed-accession skips, series success
  and retry, partial failure recording, and all-CIK nonzero exit behavior.
- Full Python 3.14 suite: 91 tests passed in 1.282 seconds with zero expected
  failures. `compileall` and `git diff --check` passed.
- Real backfill, all 45 configured CIKs: 45 succeeded, 0 failed; 1,188 filings
  processed; 5,482 events added; 3,987 series resolved; 0 unresolved. Wall
  time: 6,735.678 seconds (1h 52m 16s).
- Immediate incremental, July 17-20 overlap: 45 succeeded, 0 failed; 5
  processed filings skipped; 0 new filings/events/series. Wall time: 38.921
  seconds with 62 actual HTTP requests counted at `requests.Session.get`.
- ETF Opportunities Trust (`0001771146`), June 19-July 2: persisted and live
  paths each produced 14 snapshot rows. They matched exactly on event ID,
  ticker/name, filing and SEC identity, vehicle/scope, ticker provenance,
  effectiveness fields, amendment history, and prior-effectiveness evidence.
  The confirming live fetch took 49.753 seconds.
- Local ignored `data/etf_dash.sqlite`: 4,059,136 bytes (3.871 MiB). Do not
  commit it in Increment 13a.
- `MODULE_CONTRACT_VERSION` remains 12. No changes were made to `app.py`,
  `readiness.py`, `vehicle_classifier.py`, or any pre-existing test.

## Increment 13b

1. Added `.github/workflows/ingest.yml`, scheduled for 7:00 AM and 4:00 PM
   America/New_York with a daylight-saving-aware gate, manual dispatch,
   serialized runs, Python 3.14, a 30-minute timeout, and bot commits only when
   `data/etf_dash.sqlite` changes.
2. Committed the validated 3.871 MiB initial store containing 5,482 filing
   events. SQLite WAL, SHM, and journal sidecars remain ignored.
3. Full suite passed with 91 tests. Commit `1e3724a` is pushed and is the base
   for Increment 13c.

## Increment 13c

### Store-First Runtime

1. Added `app_data.py`, a Streamlit-free runtime data layer. It resolves the
   committed store from the app's project root, serves covered filing windows
   without network calls, and falls back to the existing pure-live path when
   the store is missing, empty, or unreadable.
2. Requests extending beyond the latest successful ingest receive a live SEC
   top-up beginning three days before the stored end bound. Stored and live
   events merge by `event_id`, with one row retained per event across the
   overlap. A failed or partial top-up returns stored coverage with a visible,
   non-fatal warning and failed per-CIK status rather than crashing.
3. Added public `sec_filings.finalize_event_rows()` and routed both the pure-live
   and store-first paths through the same SEC-mapping enrichment, later-filing
   ticker enrichment, date filtering, and timestamp ordering pipeline.
4. `app.py` now reads the series registry once per cached render. Series IDs
   already in the store require no live lookup; missing IDs retain the existing
   cached SEC fallback and existing visible failure handling.
5. `load_filing_events` retains its downstream tuple contract, including
   filing statuses, mapping status, and fetch timestamp. Pure store responses
   synthesize successful per-CIK statuses labeled as served from the store.

### Tests And Acceptance

- Added five tests in `tests/test_app_data.py`: offline store parity, overlap
  top-up/dedup, missing-store live fallback, non-fatal offline top-up, and
  store-first series-age lookup with one-call live fallback for a miss.
- Full Python 3.14 suite: 96 tests passed in 3.78 seconds. `compileall` and
  `git diff --check` passed.
- Network-disabled ETF Opportunities Trust (`0001771146`), June 19-July 2:
  store-first and direct finalized-store paths each produced 14 events and 14
  snapshot rows. Event IDs and compared ticker, vehicle/scope, effectiveness,
  and amendment-history fields matched exactly; the live function was never
  invoked.
- `MODULE_CONTRACT_VERSION` remains 12 in all three modules because this is a
  data-source change only; no event or snapshot dictionary shape changed.
- Increment 13c was approved and pushed as commit `447d7a0`.

## Increment 14

### Launch-Readiness Taxonomy

- Replaced ticker-led readiness with a timing-first eight-state model:
  `Initial review`, `Upcoming launch`, `Recently launched`, `Launched (stale)`,
  `Existing fund amendment`, `Routine 485(b) update`,
  `Effective (amendment)`, and `Timing undetected`.
- `S-1` and `N-1A` rows remain `Initial review`; Rule 485 timing determines the
  future, recent, stale, routine, amendment, and undetected states. The
  recently-launched window is inclusive through 30 days.
- Added `needs_ticker` as an orthogonal boolean, so ticker availability no
  longer changes the readiness state. Series-age and prior-effectiveness
  overrides continue to identify existing-fund amendments.
- Updated the app's visibility filters, summary card, table, and workbook to
  use the new taxonomy. Increment 18 later narrowed the default-visible set.
- Commit: `a0fc41c`. No module-contract or data-version bump was required
  because readiness remains a post-cache presentation step.

## Increment 15

### Deep Rule 485 Effectiveness Recognition

- Replaced the blind 120,000-character parser slice with an anchor search over
  at most the first 1,000,000 characters, followed by a small bounded window
  around the Rule 485 facing-sheet election. Documents without an anchor keep
  the legacy first-120,000-character fallback.
- Added precise nearest-marker handling for inline checked and unchecked ballot
  boxes while retaining the existing table-row and designated-date paths.
- The diagnostic sample covered 40 store-blank `485BPOS` accessions: 29 had
  elections beyond 120,000 characters, two had direct/inline elections within
  that range, and nine used Wingdings-marker or designated-date variants. With
  1,000,000-character input, the sample improved from 40 blanks to zero.
- Added accession-backed Defiance, Dimensional, ETF Opportunities Trust, and
  Fidelity fixtures plus leakage and regression tests.
- Commit: `dcc4e36`. `MODULE_CONTRACT_VERSION` remained 12.

## Increment 16

### Version-Aware Reprocessing

- Raised all primary-document fetch sites to
  `PRIMARY_DOCUMENT_MAX_CHARS = 1_000_000`; filing-index fetches remained
  bounded at 300,000 characters.
- Introduced dedicated `PARSER_VERSION = 13`, stamped it on filing events and
  processed accessions, and taught the ingest to reprocess accessions stored
  under an older parser version instead of skipping them.
- Added ingest and store tests for parser-version lookup, stamping,
  reprocessing, and in-place event updates. `MODULE_CONTRACT_VERSION` stayed 12
  and `SCHEMA_VERSION` stayed 1.
- A subsequent full-store Increment 16b reprocess trial exposed identity
  over-extraction from exhibit lists when the full one-million-character text
  reached the name/ticker parsers. That data trial was discarded and never
  committed. Increment 17 contained identity extraction before the targeted
  effectiveness heal documented below.
- Commit: `70e4976`.

## Increment 16c

### Windowed Backfill

- Added optional `--days N` support to the backfill CLI and ingest bounds, with
  the existing 365-day backfill retained when the option is omitted.
- The option affects backfill mode only and is harmlessly ignored for
  incremental runs. This enabled bounded parser-version reprocessing of the
  recent launch window.
- Commit: `32cf41f`. No version constants changed.

## Increment 17

### Bounded Identity Extraction

- Added `PRIMARY_IDENTITY_MAX_CHARS = 300_000` and limited primary-document
  name, ticker, and filer extraction to prospectus front matter. This prevents
  exhibit lists, sub-advisory agreements, and Schedule A entries from becoming
  false fund events.
- Rule 485 effectiveness parsing still receives the full fetched
  one-million-character document, preserving Increment 15's deep election
  recognition.
- Bumped `PARSER_VERSION` from 13 to 14 because parsed event identities and
  values can change. `MODULE_CONTRACT_VERSION` and `SCHEMA_VERSION` remained
  unchanged.
- Commit: `0858b4e`.

## Increment 18

### Not-Yet-Effective Default View

- Moved `Recently launched` from the default-visible set to the hidden set.
  The default is now exactly `Initial review` plus `Upcoming launch`.
- The hidden set contains all six already-effective, routine, amendment, stale,
  and timing-undetected states. Tests lock a complete, disjoint partition of
  all eight readiness states.
- Added recently launched rows to the app's hidden-count caption breakdown.
- Commit: `7c1616e`. No version constants changed.

## Local-Only Files

- `.claude/` remains available locally but is ignored and untracked.
- Watch item only: structured series-table tickers pass through
  `INVALID_TICKERS`, which could reject a legitimate ticker that collides with
  a denylisted word such as `MID`. Do not change this without a future approved
  increment.
- Store-first reads do not re-fetch or reapply the SEC fund-ticker mapping;
  they rely on ingest-time mapping. A row stored as `Not Listed` during a
  temporary mapping outage will not self-heal at read time as the pure-live path
  would. This is accepted for Increment 13c and should be revisited only in a
  separately approved increment.
- Store-first live top-up currently extends only beyond the store's latest end
  bound. It does not back-fill requests before the trailing-12-month store
  floor. This remains safe while the date picker is restricted to the current
  calendar year. Any future prior-year date support must add a floor-side
  top-up before that restriction is removed.

## Targeted Effectiveness Heal

- Reprocessed the 2026-04-23 through 2026-07-22 window under
  `PARSER_VERSION = 14` using the 90-day backfill option.
- Reprocessed 311 filings. Stored filing events increased from 5,482 to 5,503,
  safely passing the 6,100-event sanity gate.
- Accessions with at least one blank-effectiveness row in the 90-day window
  fell from 41 to 8. The parser-version orphan check returned zero rows.
- Global X LLM ETF, Global X Asia Semiconductor ETF, and Global X MLCC &
  Electronic Components ETF now carry Rule 485(a)(2) effectiveness timing and
  appear as `Upcoming launch` in the default view.
- Known deferred gap: WisdomTree Global Alpha Fund and WisdomTree Efficient
  Long/Short U.S. SmallCap Equity Fund now have effectiveness timing but remain
  `Other / unknown`, so they do not pass the ETF vehicle gate. Increment 19
  will address this classification separately.

## Increment 19

### Exchange-Listed ETF Signal

- Added conservative, self-referential exchange-listing detection against the
  bounded primary-document front matter. Strong signals include the fund being
  an exchange-traded fund or its own shares being listed or traded on an
  exchange; comparison-only mutual-fund language does not qualify.
- Passed the transient `exchange_listed` signal into vehicle classification at
  parse time, then removed it before emitting the event. The signal is a
  low-precedence ETF rescue, so mutual-fund class names and five-letter
  mutual-fund tickers still win.
- Read-time vehicle normalization now preserves an authoritative stored ETF or
  mutual-fund-share-class value when current evidence would otherwise degrade
  it to `Other / unknown`; stronger contrary evidence can still reclassify it.
- Added a real WisdomTree `485APOS` fixture and classifier, parser, integration,
  and non-downgrade tests. Bumped `PARSER_VERSION` from 14 to 15 while leaving
  `MODULE_CONTRACT_VERSION` and `SCHEMA_VERSION` unchanged.
- Commit: `3489df0`.

## Increment 19b

- Reprocessed the 2026-04-24 through 2026-07-23 window under
  `PARSER_VERSION = 15` to apply the exchange-listed ETF classifier.
- Reprocessed 315 filings. Stored filing events increased from 5,528 to 5,537,
  safely passing the 6,100-event sanity gate.
- Fifty-five events changed from `Other / unknown` to `ETF`: 53 ProShares
  registrations and the two targeted WisdomTree funds. Independent review
  found no wrong-direction or mutual-fund vehicle flips.
- The parser-version orphan check returned zero rows, and SQLite integrity
  remained healthy.
- WisdomTree Global Alpha Fund, WisdomTree Efficient Long/Short U.S. SmallCap
  Equity Fund, and future-effective ProShares registrations now classify as
  `Upcoming launch` through the store-first snapshot and readiness pipeline.

## Increment 20

### ETF Share-Class Watch

- Added a read-time boolean `etf_share_class` column in
  `add_launch_readiness_columns` (`readiness.py`). It flags an ETF-vehicle
  snapshot row whose `series_id` also has at least one
  `MUTUAL_FUND_SHARE_CLASS` sibling row in the same snapshot window: a
  multi-share-class fund with both an ETF class and traditional mutual-fund
  classes. Only ETF-vehicle rows are flagged; mutual-fund and other rows remain
  `False`. Series IDs are normalized both when building the qualifying set and
  when testing membership.
- `app.py` adds an "ETF Share Classes" summary card counted from `visible_df`,
  so it follows the readiness toggle, and includes `etf_share_class` in the
  on-screen table and Excel export immediately after `vehicle`.
- V1 limitation, also documented in code: both sibling vehicle types must
  appear in the selected snapshot window. A future SEC-mapping-backed pass
  could catch classes whose siblings did not file in-window. The mutual-fund
  -> ETF conversions half of this competitive-signal vector remains deferred;
  it needs N-14/proxy forms or conversion-language parsing and is not
  detectable from the current 485-only data.
- No version bumps: `add_launch_readiness_columns` runs post-cache, so
  `MODULE_CONTRACT_VERSION` (12), `PARSER_VERSION` (15), `DATA_VERSION`, and
  `SCHEMA_VERSION` (1) are unchanged.
- Independent verification on the committed store found 12 flags, all Vanguard
  dual-class index-fund ETF Shares such as VOO, with 100% `vehicle == ETF` and
  zero false flags. Commit `7f03592` was rebased to `da3a822` over a concurrent
  scheduled store commit and pushed.

## Increment 21

### README Repositioning

- Rewrote `README.md` around the shipped product: a primary-SEC filing radar
  for not-yet-effective ETF launches, not a price or portfolio dashboard.
- Documented the eight readiness states, the store-first runtime, scheduled
  ingest and parser-version repair model, current UI/workbook behavior,
  limitations, roadmap, and review entry points.
- Commit: `ceb7593`. Documentation only; no runtime or version change.

## Increment 22

### Retired Legacy Rails

- Deleted the unused ETF.com/ETFdb scraper, broad-news helper, seed/status
  files, legacy refresh script, and three one-off CIK audit artifacts after a
  repository-wide reference check confirmed no live dependency.
- Replaced the README's legacy-file table with a concise historical note. The
  product now documents primary SEC filings as its sole data source.
- The commit removed nine dead files and 3,442 lines from those files (3,455
  total deletions including the README edit).
- Commit: `5ea9b75`. No live module, dependency, workflow, store, or version
  change.

## Increment 23

### Deterministic Launch-Pipeline Brief

- Added the Streamlit-free `scripts/generate_launch_brief.py`. It builds the
  current-year store-first snapshot, applies the same series-age and readiness
  rules as the app, and keeps only `Initial review` and `Upcoming launch` rows.
- Added stable SEC-identity/name fallback keys and a JSON state file to compute
  new entries since the previous brief. Markdown output includes pipeline
  totals, top filers and themes, and detailed new-fund bullets.
- The generator is deterministic for a supplied date, uses no LLM or external
  API, and writes `data/launch_brief.md` plus
  `data/launch_brief_state.json`. Both baseline artifacts are committed.
- Commit: `42bbe77`.

## Increment 24

### Published Launch Brief

- Added Streamlit-free `app_data.load_launch_brief()` with missing, empty, and
  read-error handling. `app.py` reads the committed markdown and displays it in
  a collapsed `Launch Pipeline Brief` expander above the search workflow.
- The panel is read-only and notes that it reflects the last scheduled ingest,
  so it may lag live search results by a few hours. A missing brief produces no
  panel and no error.
- The scheduled ingest now regenerates and stages the brief and state inside
  the existing store-changed conditional, committing all three data artifacts
  together. Quiet ingest runs still create no commit.
- Commit: `6859563`. No dependency or version change.

## Current State (2026-08-07)

- Published code is current through Increment 24 at commit `6859563`; local
  `sync-main` and `origin/main` matched before Increment 25 began.
- Committed store integrity is `ok`: 5,715 events across 1,263 accessions, with
  filing dates from 2025-07-21 through 2026-08-05. Event parser versions are
  v12=4,330 / v14=5 / v15=1,380; processed-accession versions are v12=877 /
  v14=3 / v15=383.
- The committed launch brief is dated 2026-08-07 and contains 234 forward
  pipeline rows, all `Upcoming launch`, establishing the first saved brief
  baseline.
