# ETF Dash

ETF Dash is a primary-source SEC filing radar for new ETF registrations and
launches before exchange listing, organized by legal filer, registrant, and
series trust.

It turns S-1, N-1A, 485APOS, and 485BPOS filings into a current ETF launch
pipeline with effectiveness timing, amendment history, SEC series/class
identity, vehicle classification, ticker development, and an Excel-ready
snapshot. It is not a price, portfolio, or holdings dashboard.

- Live site: [etfdash.streamlit.app](https://etfdash.streamlit.app/)
- Repository: [halestorm9352/ETF-Dashboard](https://github.com/halestorm9352/ETF-Dashboard)
- Detailed implementation history: [HANDOFF.md](HANDOFF.md)
- Runtime: Python 3.14
- Local project root: `C:\Users\jhale\Desktop\ETF Dashboard`

## Mission

The core objective is a live snapshot of ETF activity anchored in SEC filings.
Filings are the primary evidence because they reveal legal registrants, series
trusts, amendments, effectiveness timing, ticker development, and potential
launch activity before or around public announcements.

The organizing perspective is the legal filer, registrant, or series trust.
That perspective matters for understanding service-provider decisions,
including custody, fund administration, and transfer agency relationships.
Consumer-facing brands remain useful competitive signals, particularly when
assessing smaller issuers and their effect on established firms such as
ProShares, but sponsor branding is not the primary identity model.

The product is designed to:

1. Search SEC filing activity by legal filer and selected date range.
2. Retain every detected filing event as source history.
3. Derive one current, amendment-aware snapshot row per fund identity.
4. Surface effectiveness timing, launch status, ticker status, vehicle, theme,
   and ETF share-class signals.
5. Export one review-ready Excel workbook.

Later contextual data should enrich this filing product rather than become
separate competing rails.

## Core Invariant

> Filing events are retained as source history; the product presents one
> latest, amendment-aware snapshot row per fund identity.

The current snapshot identity uses SEC identifiers where available:

```text
(SEC CIK, series_id, class_id) for standalone ETF classes
(SEC CIK, series_id) for parent-scoped mutual-fund classes
(SEC CIK, normalized fund name) only when SEC IDs are absent
```

Identity scope is stabilized for each class across its filing history. Filing
events remain separate evidence even when several class rows roll up to one
parent-series snapshot identity.

### Dual-Vehicle Series

A series that contains both an ETF class and traditional mutual-fund classes
intentionally produces two snapshot rows:

1. The ETF class remains a standalone class identity and displays its ETF name
   and ticker.
2. The mutual-fund classes roll up under the parent series identity and display
   the parent series context.

This is intentional, not a duplicate. The rows represent two vehicle types and
two competitive signals within the same legal series.

## Current Experience

The Streamlit page provides:

- Issuer segments: `All`, `Top 3`, `The Field`, and `Series Trusts`.
- Issuer groups mapped to configured SEC CIKs.
- Start and end dates within the current calendar year.
- A manual Search action and a one-search `Force refresh` option.
- A stable `Data as of` timestamp displayed in US Eastern time.
- Per-filer coverage reporting and visible partial-failure warnings.
- A not-yet-effective default view with a toggle labeled
  `Include already-effective, routine & undetected rows`.
- Five summary cards:
  - `Funds Loaded`
  - `Tickers Listed`
  - `Distinct Filers`
  - `Upcoming Launches`
  - `ETF Share Classes`
- Theme counts inferred from fund names.
- One latest-snapshot table and one native `.xlsx` download.

The table and workbook include the `etf_share_class` flag immediately after
`vehicle`. Ordinary identical searches reuse the 30-minute cache and retain the
original fetch timestamp. Force refresh bypasses that cache once and repopulates
it for subsequent searches.

## Filing and Snapshot Model

A filing event is one filing occurrence for one detected fund. Events include
stable source metadata where available:

- `event_id` and `accession_number`
- filer CIK, form, filing date, acceptance timestamp, and SEC link
- fund, class, and parent-series names
- `series_id`, `class_id`, vehicle, and identity scope
- `ticker_at_filing`, current ticker, and ticker source
- Rule 485 effectiveness basis, days, designated date, and label

`ticker_at_filing` is immutable evidence. The SEC fund-ticker mapping enriches
identified rows through exact CIK + series/class joins. ID-less rows may use a
bounded later-filing fallback without changing the filing-time value. If the
mapping is unavailable, the result metadata and UI warn that ticker coverage
may be incomplete.

`derive_latest_fund_rows()` copies the event list, selects the newest row for
each stabilized identity, and adds:

- `filing_event_count`
- `amendment_count`
- `filing_form_history`
- prior-effective-485BPOS evidence

The public workbook contains one latest row per fund or parent-series identity,
including ticker status, fund/class identity, vehicle, ETF share-class flag,
theme, filer, filing history, effectiveness, readiness, and the SEC link.

## Forms and Effectiveness

Tracked forms:

```text
S-1
N-1A
485APOS
485BPOS
```

The parser reads checked filing context instead of assuming timing from the
form name. It recognizes:

- Immediate effectiveness under Rule 485(b).
- 60 days under Rule 485(a)(1).
- 75 days under Rule 485(a)(2).
- A designated effective date under Rule 485(a) or Rule 485(b).

The 75-day period is one possible Rule 485 path, not a universal ETF launch
rule.

Effectiveness scanning is anchor-aware and can inspect the first 1,000,000
characters, allowing the election to appear beyond a conventional cover-page
slice. Identity and named-ticker extraction use only the first 300,000
characters of the primary document so exhibit lists, Schedule A material, and
sub-advisory agreements do not become false funds. The same bounded front
matter supplies a conservative signal when a tickerless fund describes its own
shares as exchange listed or exchange traded.

## Launch Readiness

`readiness.py` treats detected timing as the primary state axis. Ticker presence
is orthogonal and appears in the boolean `needs_ticker` field rather than
changing the readiness state.

Current states:

- `Initial review`: an S-1 or N-1A initial-registration filing.
- `Upcoming launch`: a new-pipeline ETF with a detected future effective date.
- `Recently launched`: a new-pipeline ETF whose detected effective date is
  today or within the previous 30 days.
- `Launched (stale)`: a new-pipeline ETF whose detected effective date is more
  than 30 days old.
- `Existing fund amendment`: a pipeline-looking filing overridden by prior
  effectiveness evidence or a series first registered more than 18 months
  before the search start.
- `Routine 485(b) update`: an effective history made entirely of 485BPOS
  filings rather than evidence of a new fund.
- `Effective (amendment)`: another already-effective amendment history.
- `Timing undetected`: no supported effectiveness election or date was found.

The default view is deliberately narrow: it shows only `Initial review` and
`Upcoming launch`, the two not-yet-effective states. Recently effective,
stale, routine, existing-fund, other effective-amendment, and undetected rows
remain available through the readiness toggle.

### ETF Share-Class Watch

The read-time `etf_share_class` flag identifies ETF rows whose normalized
`series_id` also has a `Mutual fund share class` sibling in the same snapshot.
Only the ETF row is flagged. This surfaces multi-share-class structures without
removing or conflating the parent mutual-fund row.

The current watch requires both vehicle types to appear in the selected window.
It does not yet infer missing siblings from the SEC mapping, and it does not
detect mutual-fund-to-ETF reorganizations.

## Persistent Filing Store

The application is store-first. A committed SQLite database at
`data/etf_dash.sqlite` holds parsed filing events, processed-accession history,
series registration dates, and ingest-run audit records. `store.py` is the
UI-agnostic standard-library boundary, so the persistence layer can be reused
by a future non-Streamlit interface.

### Runtime Read Path

`app_data.py` resolves the database from the project directory rather than the
process working directory:

1. Load events for the requested CIKs and dates from SQLite.
2. Read the last successful ingest bound.
3. If the requested end date extends beyond that bound, fetch only a live SEC
   tail beginning three days before the bound.
4. Merge stored and live events by `event_id`, with the live row winning an
   overlap collision.
5. Run both sources through the same final ticker enrichment, bounds filtering,
   ordering, and snapshot pipeline.

A covering store produces zero filing-network calls. If the store is missing
or empty, the app falls back to the existing live path. If a top-up fails, the
stored snapshot remains available with a non-fatal warning. Series registration
dates are also served from the store before any live fallback.

### Scheduled Ingest and Reprocessing

`.github/workflows/ingest.yml` runs the incremental ingest at approximately
7:00 AM and 4:00 PM America/New_York and commits the updated SQLite file through
the GitHub Actions bot. The ingest uses a three-day overlap, skips accessions
already processed by the current parser, resolves missing series ages, records
partial failures, and remains behind the shared SEC rate limiter.

`PARSER_VERSION = 15` is stamped on both event rows and processed accessions.
When parser behavior changes, a higher version causes older accessions to be
re-fetched and reprocessed in place. The CLI supports:

```powershell
python scripts/ingest_filings.py --incremental
python scripts/ingest_filings.py --backfill
python scripts/ingest_filings.py --backfill --days 90
```

Raw SEC documents are not archived. Accession numbers and parser versions are
the breadcrumbs for deterministic re-fetching and repair.

### SQLite Schema

`SCHEMA_VERSION = 1` contains five tables:

| Table | Purpose |
| --- | --- |
| `store_meta` | Schema version, creation time, and backfill floor. |
| `filing_events` | Parsed source events keyed by `event_id`, including SEC identity, ticker provenance, vehicle, effectiveness, ingest time, and parser version. |
| `processed_filings` | Accession-level parser-version and event-count ledger. |
| `series_registry` | First-filing dates keyed by `series_id`. |
| `ingest_runs` | Bounds, coverage, counts, timestamps, and error summaries for each run. |

Snapshot-derived amendment and readiness fields remain read-time values rather
than stored columns.

### Current Store Snapshot

As recorded on 2026-08-04, the committed store contained:

- 5,694 filing events across 1,259 accessions.
- Filing dates from 2025-07-21 through 2026-07-31.
- Event parser versions: v12=4,330, v14=5, v15=1,359.
- Processed-accession versions: v12=877, v14=3, v15=379.
- SQLite integrity result: `ok`.

The latest measured current-year snapshot had 248 default-visible upcoming
rows, 461 timing-undetected rows, and 12 ETF share-class flags. The share-class
flags were established Vanguard dual-class index funds and therefore appeared
only when the already-effective toggle was enabled.

## Data Flow

```text
Scheduled GitHub Actions ingest
  -> configured SEC CIK universe
  -> SEC submissions, filing indexes, and bounded primary documents
  -> parsed source events + parser-version/accession ledger
  -> committed SQLite store

Streamlit search
  -> store events for selected CIKs and dates
  -> optional live SEC top-up for the uncovered tail
  -> event_id merge and common finalization
  -> exact SEC ticker-map enrichment + bounded ID-less fallback
  -> vehicle normalization and identity-scope stabilization
  -> latest row per fund identity with amendment history
  -> timing-first readiness, theme, and ETF share-class enrichment
  -> toggle-controlled table and Excel workbook
```

Each live CIK operation returns rows plus a status containing filer identity,
success/failure, row count, and an error summary. Healthy filer results survive
when another CIK fails, so the UI distinguishes complete from partial coverage.

## Active Files

All paths are relative to `C:\Users\jhale\Desktop\ETF Dashboard`.

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit search form, caching, coverage messages, readiness view, cards, table, and workbook. |
| `app_data.py` | Store-first runtime reads, live top-up merge, offline grace, and series-registry fallback. |
| `config.py` | CIK universe, groups, forms, worker limits, parser windows, and data versions. |
| `store.py` | Streamlit-free SQLite schema and filing-event, accession, series, and ingest-run APIs. |
| `scripts/ingest_filings.py` | Backfill, targeted reprocessing, and overlap-aware incremental ingest CLI. |
| `.github/workflows/ingest.yml` | Twice-daily Eastern-time ingest and bot store commit. |
| `sec_filings.py` | SEC retrieval, event construction/finalization, ticker enrichment, and snapshot derivation. |
| `sec_parsers.py` | Fixture-backed name, ticker, series/class, exchange-listing, and effectiveness extraction. |
| `readiness.py` | Timing-first readiness, series-age overrides, ticker flag, and ETF share-class watch. |
| `vehicle_classifier.py` | ETF, mutual-fund share-class, and unknown vehicle classification and scope rules. |
| `theme_classifier.py` | Rule-based fund-name themes and summaries. |
| `http_utils.py` | SEC headers, thread-local sessions, shared pacing, retry, and response limits. |
| `tests/test_app_data.py` | Store-only parity, top-up merge, offline fallback, and series-registry tests. |
| `tests/test_store.py` | Schema, event round-trip, idempotency, registry, and ingest-run tests. |
| `tests/test_ingest_filings.py` | Bounds, partial failures, reprocessing, and CLI behavior. |
| `tests/test_filing_events.py` | Event history, identity, enrichment, effectiveness, and failure reporting. |
| `tests/test_sec_parser_fixtures.py` | Accession-backed parser behavior for supported SEC forms and edge cases. |
| `tests/test_readiness.py` | State taxonomy, visibility, series-age overrides, and ETF share-class flag. |
| `tests/test_vehicle_classifier.py` | Vehicle precedence, parent rollup, and dual-vehicle snapshots. |
| `tests/test_data_hygiene.py` | Ticker, placeholder-class, and theme hygiene. |
| `tests/test_http_utils.py` | Shared SEC pacing and retry/final-failure behavior. |

## Performance and Reliability

Implemented safeguards include:

- Store-only reads for covered windows and a narrow live tail when needed.
- A 30-minute Streamlit cache with explicit one-search refresh.
- A shared SEC limiter targeting eight requests per second across threads.
- Retryable 403/429 handling, capped `Retry-After`, and terminal failure
  reporting.
- Bounded CIK workers and primary-document prefetch.
- Per-CIK coverage statuses and partial-result warnings.
- Version-aware accession reprocessing.
- Accession-backed parser fixtures and identity/effectiveness window guards.
- Non-fatal offline behavior when stored coverage exists.

Known limitations:

1. Rows without SEC series/class IDs still use normalized-name fallback
   identity.
2. The date picker remains limited to the current calendar year. Store top-up
   extends the trailing edge only; prior-year support would also require a
   floor-side top-up.
3. SEC layouts remain heuristic. Some non-standard 485 filings still lack a
   recognized effectiveness election and remain timing-undetected.
4. The ETF share-class watch requires both the ETF and mutual-fund sibling to
   appear in the selected snapshot window.
5. Mutual-fund-to-ETF conversions are not yet identified from N-14/proxy forms
   or conversion language.
6. Store-first reads rely on ingest-time SEC ticker mapping. A ticker missed
   during a mapping outage does not currently self-heal at read time.
7. The filer universe is maintained manually in `config.py`.
8. There is no dedicated vehicle filter in the current interface.

## Condensed Project History

ETF Dash began as a live Streamlit filing scraper, expanded SEC coverage and
multi-fund parsing, experimented with launches/news/AUM/flow rails, and then
returned to a deliberately focused filing product when those secondary rails
proved stale or crowded.

The reviewed increments through Increment 20 established stable cache and
failure semantics, fixture-backed parsing, SEC series/class identity, vehicle
classification, amendment-aware snapshots, and reproducible runtime versions.
The major second arc added the persistent SQLite store and scheduled ingest,
refactored readiness around effectiveness timing, extended effectiveness
parsing beyond the cover window, bounded identity extraction to prevent exhibit
over-extraction, made not-yet-effective funds the default view, detected
tickerless exchange-listed ETFs, and added the ETF share-class watch.

For commit-level decisions, benchmarks, operational heals, review verdicts,
and watch items, use [HANDOFF.md](HANDOFF.md) and `git log --oneline`.

## Approved Product Decisions

- Legal filers, registrants, and series trusts are the primary organization.
- Filing events remain source history; snapshots are always derived.
- Mutual-fund-looking rows are retained because ETF share classes and
  reorganizations are competitive signals.
- Placeholder class-only names never become standalone snapshot identities.
- Filing context is more authoritative than form name for effectiveness.
- The default view focuses on funds that are not yet effective.
- The workbook remains a crucial deliverable, and the page stays deliberately
  simple.
- News remains on hold because prior implementations crowded the core workflow.

## Product Roadmap

Shipped foundations include the persistent filing store, scheduled incremental
ingest, store-first runtime, timing-first launch view, exchange-listing vehicle
signal, and ETF share-class watch.

Deferred vectors:

1. **Mutual-fund-to-ETF conversions.** Add N-14/proxy coverage or conservative
   conversion-language detection; the share-class watch alone does not cover
   reorganizations.
2. **Issuer net flows from primary sources.** Research N-PORT-derived shares
   outstanding and NAV, including source latency, before any UI work.
3. **Aggregate AUM growth.** Compute for the selected legal filer and period
   from a stable, permitted source.
4. **Form 8-A precision.** Use listing-registration evidence to distinguish an
   effective registration from an actual exchange-listing date.
5. **Theme coverage.** Expand fixture-backed classification without weakening
   existing precision.
6. **Filer-focused news.** On hold indefinitely.

Any new rail must preserve the simple search -> snapshot -> workbook flow.

## Legacy and Reference Files

The removed launch, broad-news, AUM, and flow rails remain only as inactive
references:

| File | Current status |
| --- | --- |
| `etfcom.py` | Legacy launch, AUM, flow, and news logic; not imported by the page. |
| `news_sources.py` | Legacy broad-news helpers; not imported by the page. |
| `etfcom_launches_seed.csv` | Historical launch fallback data. |
| `etfcom_launches_status.json` | Historical launch freshness metadata. |
| `etfcom_news_seed.csv` | Historical news fallback data. |
| `scripts/refresh_launches_snapshot.py` | Legacy refresh script with no active workflow. |
| `cik_*_2026-04-22.json` | Historical CIK/form audit artifacts. |

The local `.claude/` directory is ignored and is not part of the published
application repository.

## Reproducible Setup

From PowerShell:

```powershell
Set-Location 'C:\Users\jhale\Desktop\ETF Dashboard'
& 'C:\Users\jhale\AppData\Local\Python\bin\python3.14.exe' -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Direct runtime dependencies use bounded ranges in `requirements.txt`.
Streamlit Community Cloud and local development both use Python 3.14 as
declared by `.python-version`.

## Verification

Run from the project root:

```powershell
python -m unittest discover -s tests -v
python -m compileall app.py app_data.py config.py http_utils.py readiness.py `
  sec_filings.py sec_parsers.py store.py theme_classifier.py `
  vehicle_classifier.py scripts\ingest_filings.py tests
git diff --check
```

Current verified result:

```text
Ran 124 tests
OK
```

Coverage includes store/live parity, top-up deduplication, offline grace,
version-aware reprocessing, SEC pacing and retry behavior, amendment-aware
identity, ticker provenance, vehicle precedence, readiness taxonomy,
ETF-share-class detection, effectiveness elections, bounded identity parsing,
and accession-backed parser fixtures.

Current version facts:

- `MODULE_CONTRACT_VERSION = 12`
- `PARSER_VERSION = 15`
- `SCHEMA_VERSION = 1`
- `DATA_VERSION = 2026-07-20-increment-12-new-fund-scope-v8`

## Review Guide

Recommended review order:

1. `README.md` for product purpose, current behavior, architecture, and limits.
2. `HANDOFF.md` for the increment-by-increment record and accepted watch items.
3. `app.py` and `app_data.py` for the UI, cache, store-first read path, and
   workbook contract.
4. `store.py`, `scripts/ingest_filings.py`, and `.github/workflows/ingest.yml`
   for persistence and scheduled ingestion.
5. `sec_filings.py`, `sec_parsers.py`, and `vehicle_classifier.py` for SEC
   evidence, identity, extraction, and vehicle behavior.
6. `readiness.py` for the timing-first state machine and share-class watch.
7. `tests/` and `tests/fixtures/sec/README.md` for protected behavior and
   accession provenance.

The most important review questions are whether source events remain immutable
history, snapshot identity remains amendment-aware, store and live paths stay
equivalent, partial failures remain visible, and heuristic parser changes stay
fixture-backed.
