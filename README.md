# ETF Dash

ETF Dash is a Streamlit research tool for monitoring ETF registration activity
from SEC filings. It preserves filing events as source history and presents one
latest, amendment-aware snapshot row per detected fund for the selected period.

- Live site: https://etfdash.streamlit.app/
- GitHub: https://github.com/halestorm9352/ETF-Dashboard
- Local project root: `C:\Users\jhale\Desktop\ETF Dashboard`
- Published branch: `main`
- Local working branch: `sync-main`
- Current published commit: `6ce3c3f`
- Runtime: Python 3.14
- Current test suite: 62 tests

## Mission

The core objective is a live snapshot of ETF activity anchored in SEC filings.
Filings are the primary evidence because they show legal registrants, series
trusts, amendments, effectiveness timing, ticker development, and potential
launch activity before or around public announcements.

The organizing perspective is the legal filer, registrant, or series trust.
That perspective is important for understanding service-provider decisions,
including custody, fund administration, and transfer agency relationships.
Consumer-facing brands remain useful competitive signals, particularly when
assessing smaller issuers and their effect on established firms such as
ProShares, but sponsor branding is not the primary identity model.

The intended product is:

1. Search SEC filings by legal filer and selected date range.
2. Retain every detected filing event as source history.
3. Derive one current period snapshot row per fund.
4. Show amendment history, effectiveness context, ticker status, theme, and
   launch readiness.
5. Export one review-ready Excel workbook.

Three later contextual vectors should support the filing snapshot:

1. Focused news about the selected filer or fund, prioritizing official press
   releases.
2. Aggregate AUM growth for the selected filer over the searched period.
3. Aggregate net fund flows for the filer and period, using stable and
   permitted sources.

These vectors should enrich the filing product rather than become separate
competing rails.

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

This is intentional, not a duplicate: the rows represent two vehicle types and
two competitive signals within the same legal series.

## Current Experience

The Streamlit page provides:

- Issuer segments: `All`, `Top 3`, `The Field`, and `Series Trusts`.
- One or more issuer groups mapped to configured SEC CIKs.
- Start and end dates within the current calendar year.
- A manual Search action.
- A `Force refresh` checkbox for bypassing the normal 30-minute cache.
- A coverage caption after each search:
  `Searched N filers; K succeeded, M failed.`
- A visible partial-coverage warning listing failed filers.
- Summary cards for funds loaded, listed tickers, distinct filers, and
  launch candidates.
- Theme counts inferred from fund names.
- One latest-snapshot table.
- One native `.xlsx` download named for the selected date range.

Ordinary identical searches reuse cached results and retain the original
`Data as of` timestamp. A forced refresh increments the refresh token once,
repopulates the cache, and resets the checkbox.
The timestamp is converted from UTC to US Eastern time and labeled `ET`.

## Filing and Snapshot Model

A filing event is one filing occurrence for one detected fund. Events include
stable metadata where available:

- `event_id`
- `accession_number`
- `ticker_at_filing`
- enriched/current `ticker`
- `series_id`, `series_name`, `class_id`, and `class_name`
- vehicle classification and identity scope
- filer and CIK
- form and filing date
- filing link
- detected Rule 485 effectiveness context

`ticker_at_filing` is immutable evidence. The SEC fund-ticker mapping enriches
identified rows through exact CIK + series/class joins. ID-less rows may still
use the bounded later-filing fallback without changing `ticker_at_filing`.
When the SEC mapping is unavailable, the result metadata and UI state that
tickers may be incomplete; Force refresh retries the mapping fetch.

`derive_latest_fund_rows()` copies the event list, retains the newest row for
each current identity, and adds:

- `filing_event_count`
- `amendment_count`
- `filing_form_history`

The public workbook contains one latest row per fund and includes:

- ticker and fund name
- class name, vehicle, series ID, and class ID
- inferred theme
- filer and form
- filing stage
- event and amendment counts
- filing-form history
- filing date
- effectiveness label and earliest detected effective date
- days to readiness
- launch-readiness state
- SEC filing link

## Forms and Effectiveness

Tracked forms:

```text
S-1
N-1A
485APOS
485BPOS
```

The parser uses checked filing context rather than assuming timing from the
form name alone. It currently detects:

- Immediate effectiveness under Rule 485(b).
- 60 days under Rule 485(a)(1).
- 75 days under Rule 485(a)(2).
- A designated effective date under Rule 485(a) or Rule 485(b).

The 75-day period is one possible Rule 485 path, not a universal ETF launch
rule.

## Launch Readiness

Readiness is calculated in `readiness.py` from snapshot rows that already
contain period-specific `filing_form_history`.

Current states:

- `Initial review`
- `Timing not detected`
- `Needs ticker`
- `Waiting on effectiveness`
- `Launch candidate`
- `Effective (485(b) update)`
- `Effective (amendment)`

`Launch candidate` requires all of the following:

1. A ticker is present.
2. The detected effective date has arrived.
3. The selected-period history starts with `S-1`, `N-1A`, or `485APOS`,
   providing evidence of a new fund in that period.
4. The row is classified as an ETF.

An already-effective history containing only `485BPOS` is labeled
`Effective (485(b) update)`. Any other already-effective amendment history
that does not qualify as a launch candidate is labeled
`Effective (amendment)`.

Claude replayed this logic against the saved January 1-July 16 all-issuers
export of 1,881 rows:

```text
Prior Launch Candidates:             375
Gated Launch Candidates:             127
Effective (485(b) update):           247
```

Production-equivalent live count attempts exceeded 30 and 60 minutes without
emitting an aggregate result. The offline replay is the accepted validation.

## Data Flow

```text
Streamlit filters
  -> issuer groups mapped to SEC CIKs
  -> SEC submissions JSON
  -> bounded concurrent CIK processing
  -> filing index plus primary/supporting documents
  -> fund, SEC series/class, ticker, filer, and Rule 485 extraction
  -> complete in-memory filing-event history
  -> exact SEC ticker-map enrichment plus bounded ID-less fallback
  -> vehicle reclassification and identity-scope stabilization
  -> selected-date filtering
  -> latest row per current identity
  -> period-history readiness and theme enrichment
  -> table and Excel workbook
```

Each CIK returns rows plus a status containing filer identity, success/failure,
row count, and an error summary. Healthy filer results survive when another CIK
fails. The UI therefore distinguishes complete searches from partial results.

## Active Files

All paths are relative to `C:\Users\jhale\Desktop\ETF Dashboard`.

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit UI, search form, cache wrapper, coverage messaging, summary cards, table, and workbook generation. |
| `config.py` | CIK universe, issuer groups, segments, forms, concurrency limits, data versions, and invalid ticker terms. |
| `sec_filings.py` | SEC retrieval, per-CIK status reporting, event construction, ticker enrichment, and snapshot derivation. |
| `store.py` | Streamlit-free SQLite schema and persistent event/series/run data access. |
| `scripts/ingest_filings.py` | Backfill and overlap-aware incremental SEC ingest CLI. |
| `sec_parsers.py` | HTML/text cleaning and extraction of filer names, names, tickers, series rows, supporting URLs, and Rule 485 context. |
| `readiness.py` | Filing stage, effective-date calculation, history parsing, and launch-readiness states. |
| `vehicle_classifier.py` | ETF, mutual-fund share-class, and unknown vehicle classification plus parent-series identity rules. |
| `theme_classifier.py` | Rule-based theme classification and theme summaries. |
| `http_utils.py` | Thread-local HTTP sessions, SEC headers, retry behavior, and response truncation. |
| `tests/test_filing_events.py` | Filing history, partial failure, enrichment window, Rule 485, and ticker-at-filing tests. |
| `tests/test_http_utils.py` | Shared SEC pacing, Retry-After, and terminal 403/429 behavior. |
| `tests/test_data_hygiene.py` | Invalid ticker, ambiguous ticker assignment, placeholder class, and theme tests. |
| `tests/test_readiness.py` | Launch-candidate gating and readiness-state tests. |
| `tests/test_sec_parser_fixtures.py` | Real-world SEC fixture baselines for S-1, N-1A, 485APOS, and 485BPOS extraction. |
| `tests/test_vehicle_classifier.py` | Vehicle classification, parent-series rollup, and dual-vehicle snapshot tests. |
| `requirements.txt` | Bounded direct runtime dependencies. |
| `.python-version` | Python 3.14 runtime declaration. |

## Legacy and Reference Files

The launch, broad-news, AUM, and flow rails were removed from the visible app
because their data was stale or not reliably refreshed. Some inactive source
and seed files remain as references:

| File | Current status |
| --- | --- |
| `etfcom.py` | Legacy ETF.com/ETFdb launch, AUM, flow, and news logic; not imported by the current page. |
| `news_sources.py` | Legacy broad-news helpers; not imported by the current page. |
| `etfcom_launches_seed.csv` | Historical launch fallback data. |
| `etfcom_launches_status.json` | Historical launch freshness metadata. |
| `etfcom_news_seed.csv` | Historical news fallback data. |
| `scripts/refresh_launches_snapshot.py` | Legacy refresh script; no active GitHub workflow calls it. |
| `cik_*_2026-04-22.json` | Historical CIK and form audit artifacts. |

The obsolete `.github/workflows/refresh-launches-snapshot.yml` workflow was
deleted in Increment 2.

The local `.claude/` worktree directory is ignored and is not part of the
published application repository.

## Reproducible Setup

From PowerShell:

```powershell
Set-Location 'C:\Users\jhale\Desktop\ETF Dashboard'
& 'C:\Users\jhale\AppData\Local\Python\bin\python3.14.exe' -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Direct dependencies are bounded below the next major version:

```text
requests>=2.34.2,<3
beautifulsoup4>=4.15.0,<5
openpyxl>=3.1.5,<4
streamlit>=1.59.2,<2
pandas>=3.0.3,<4
```

Streamlit Community Cloud and local development both use Python 3.14.

## Verification

Run from the project root:

```powershell
python -m unittest discover -s tests -v
python -m py_compile app.py http_utils.py readiness.py sec_filings.py sec_parsers.py `
  theme_classifier.py vehicle_classifier.py tests\test_filing_events.py `
  tests\test_data_hygiene.py tests\test_http_utils.py tests\test_readiness.py `
  tests\test_sec_parser_fixtures.py tests\test_vehicle_classifier.py
git diff --check
```

Current verified result:

```text
Ran 62 tests
OK
```

Coverage includes:

- Rule 485 60-day, 75-day, immediate, designated-date, and unchecked cases.
- Event retention and amendment-history summaries.
- Ticker enrichment without changing `ticker_at_filing`.
- Historical enrichment capped at 90 days.
- Healthy results surviving a failed CIK.
- Exchange words and false positives rejected as tickers.
- Ambiguous inferred tickers not assigned to multiple series rows.
- Legitimate single-fund inferred ticker assignment retained.
- Placeholder class-only names removed without excluding mutual funds broadly.
- Theme-classification fixes for option income, short-term, QuadPro, ladder,
  and iBonds names.
- New-fund launch gating and effective amendment states.
- Accession-sourced parser fixtures and quoted-prose IBIT extraction.
- SEC series/class identity and exact ticker-map enrichment.
- Mapping-failure visibility and immutable ticker-at-filing behavior.
- Vehicle reclassification after enrichment and class-scope stabilization.
- Dual-vehicle series producing one ETF class row and one parent mutual row.
- Empty snapshot handling and normalized naive-UTC event ordering.

## Performance and Reliability

Implemented safeguards:

- Thread-local HTTP sessions.
- A shared SEC interval limiter targeting eight requests per second across
  worker threads.
- Retryable SEC 403/429 handling with backoff and `Retry-After` support.
- Bounded concurrent CIK processing.
- Concurrent primary-document prefetch for a single selected CIK.
- Response-size limits and retries.
- Limited supporting-document retrieval.
- A 30-minute Streamlit cache with explicit force refresh.
- Per-CIK failure reporting and partial-result warnings.
- Historical ticker enrichment capped at the earlier of today or 90 days
  after the selected end date.

Known limitations:

1. All-issuers year-to-date live searches can exceed one hour.
2. There is no durable filing-event database or incremental ingestion job.
3. Rows without SEC series/class IDs still use normalized-name fallback identity.
4. ID-less historical enrichment may still inspect later filings for up to 90 days.
5. The date picker is limited to the current calendar year.
6. SEC layouts remain heuristic, although representative fixtures now lock the
   supported extraction behavior.
7. There is no dedicated vehicle filter in the current interface.

## Condensed Project History

### Foundation and SEC Expansion

The project began as a Streamlit ETF filing dashboard. Early work moved filing
discovery to SEC submissions JSON, expanded the configured ETF CIK universe,
added resilient document fallbacks, improved name/ticker extraction, and split
multi-fund filings into individual rows.

### Editorial Dashboard and Context Rails

The page evolved into a styled research dashboard with issuer filters, filing
statistics, theme summaries, news, launches, and flows. ETF.com and ETFdb
fallbacks, snapshots, and refresh jobs were introduced while parsing and CIK
coverage continued to mature.

### Return to the Core Filing Product

Launch and flow rails proved stale and were removed at commit `2e5476d`.
Filing events, amendment-aware snapshots, Rule 485 timing, launch readiness,
and export options were added. The UI was then simplified back to one latest
snapshot and one Excel download at commit `1b75d02`.

### Reviewed Increment Sequence

| Increment | Commit | Result |
| --- | --- | --- |
| 1 - Cache semantics | `8f5d6c5` | Ordinary identical searches reuse the 30-minute cache; Force refresh bypasses once; results show a stable `Data as of` time. |
| 2 - Workflow cleanup | `a66158c` | Deleted the obsolete daily launch-snapshot GitHub workflow. |
| 3 - Reproducibility | `6e5ff2f` | Added Python 3.14 declaration and bounded ranges for all direct runtime dependencies. |
| 4 - Enrichment window | `b50437d` | Capped later-filing document enrichment at `min(today, end date + 90 days)`; historical benchmark improved from 791.256s to 428.017s with the same 98 rows. |
| 5 - Partial failures | `8b040ea` | Added per-CIK statuses, cached events/statuses, coverage captions, and partial-result warnings while preserving healthy results and the legacy wrapper. |
| 5.5 - Data hygiene | `cbadd1d` | Rejected false tickers, prevented ambiguous ticker duplication, broadened placeholder-class filtering, and corrected theme terms. |
| 6 - Launch gating | `40c100d` | Required new-fund period history for Launch candidate; added effective 485(b) update and amendment states; offline count changed 375 to 127. |
| 7 - Parser fixtures | `970380d` | Added accession-sourced SEC fixtures and locked parser behavior before extraction changes. |
| 8 - Series/class identity | `bcf9427` | Added SEC series/class canonical identity and exact fund-ticker mapping joins. |
| 8.5 - Vehicle classification | `6ce3c3f` | Added ETF/mutual/unknown classification, parent-series class handling, and ETF-only launch gating. |

## Approved Decisions

- Do not exclude mutual-fund-looking rows generally. They may represent ETF
  share classes or mutual-fund-to-ETF conversions and are competitive signals.
- Placeholder class-only rows such as `Institutional Class` must not become
  standalone snapshot identities.
- Series trusts and legal entities remain central to service-provider analysis.
- Filing context is more authoritative than form name alone for effectiveness.
- Persist every event eventually and derive the current snapshot from history.
- AUM and flows should be aggregated for the selected legal filer and selected
  dates before later announcement-based views are considered.

## Remaining Product Roadmap

### Phase 2: Persistent Filing Store (decided 2026-07-20)

The next phase replaces per-search live scraping with a durable local store.
The following decisions are settled and Codex should treat them as fixed:

1. **Storage**: a single SQLite file (`data/etf_dash.sqlite`) committed to the
   repository by a scheduled GitHub Actions ingest workflow. The app reads the
   store and only fetches live filings for the gap since the last ingest.
2. **Portability is a design requirement.** All store access goes through a
   dedicated data-layer module with no Streamlit imports, and the SQLite
   schema is documented, so a future non-Streamlit UI can consume the same
   file and module unchanged. The repository is only the transport; the store
   file is the product-portable artifact.
3. **No raw document archiving.** The store holds parsed filing events plus
   accession numbers and a parser-version stamp as breadcrumbs; anything can
   be re-fetched and re-parsed from EDGAR on demand.
4. **Backfill floor: trailing 12 months** at first backfill. The date picker
   remains limited to the current calendar year; the deeper store primarily
   serves speed, series ages, and history summaries.
5. **Filer universe**: the existing CIK registry in `config.py`, maintained
   manually. No auto-discovery.
6. **Ingest cadence**: scheduled runs at approximately 7:00 AM and 4:00 PM
   Eastern each day, with GitHub's workflow-failure notifications enabled.
7. **Increment sequence**: 13a (schema + data layer + backfill/incremental
   ingest script, no app changes) -> 13b (scheduled workflow + initial store
   commit) -> 13c (app reads store with live top-up; series ages served from
   the store).

#### SQLite Schema (version 1)

`store.py` is the UI-agnostic access boundary. It imports only Python standard
library modules, creates the database when absent, and rejects a store whose
`store_meta.schema_version` differs from its supported `SCHEMA_VERSION`.

| Table | Purpose and key fields |
|---|---|
| `store_meta` | Key/value metadata keyed by `key`; records `schema_version=1`, the trailing-365-day `backfill_floor`, and `created_at`. |
| `filing_events` | Contract-v12 source events keyed by `event_id`. Includes accession, CIK, form/timestamps, fund/series/class identity, ticker provenance, vehicle, filer/link, effectiveness fields, `ingested_at`, and `parser_version`. Indexed by `(cik, date)`, `series_id`, and `accession_number`. Snapshot-derived history fields are deliberately not stored. |
| `processed_filings` | Accession-level ingest ledger keyed by `accession_number`, with CIK, form, filing date, parser version, event count, and ingest timestamp. |
| `series_registry` | Immutable first-filing dates keyed by `series_id`, with parent CIK, lookup source, and resolution timestamp. Failed lookups are not inserted and retry on the next run. |
| `ingest_runs` | Backfill/incremental audit records keyed by `run_id`, including bounds, CIK success coverage, filings/events added, timestamps, and failure summaries. |

The public store API opens/version-checks the database, upserts and loads event
dicts, tracks processed accessions, reads/writes series registration dates, and
records/reads ingest runs. `load_events()` returns the same source-event shape
as `fetch_filing_events()`, so existing read-time ticker enrichment and latest
snapshot derivation can consume persisted and live events identically.

#### Ingest CLI

Run `python scripts/ingest_filings.py --backfill` for the trailing 365 days or
`python scripts/ingest_filings.py --incremental` to resume from the last
successful end bound with a three-day overlap. Both modes reuse the live
per-CIK parser path, use bounded workers behind the shared SEC rate limiter,
skip processed accessions, resolve missing series ages, record partial failures,
and finish with SQLite `VACUUM`. Progress is written to stderr and the final
structured run report to stdout. The default database is
`data/etf_dash.sqlite`; it remains ignored through Increment 13a and will be
deliberately committed by Increment 13b.

### Later Product Vectors (deferred, in priority order)

1. **Issuer net flows from primary sources.** Explicitly wanted, explicitly a
   nice-to-have. Must come from primary/filing data (e.g., N-PORT-derived
   shares outstanding and NAV), not scraped websites. Requires a research
   spike on source latency before any UI work; monthly N-PORT data carries a
   roughly 60-day lag that must be disclosed if used.
2. **Conversions and ETF-share-class visibility** using the existing vehicle
   classification data.
3. Aggregate AUM growth for the selected filer and period.
4. Filer-focused news is **on hold indefinitely** - prior attempts crowded
   the UI without adding decision value.

### UI Principle (decided 2026-07-20)

The Excel workbook is a crucial deliverable and the page stays deliberately
simple. Prior experiments with news rails and AUM trackers crowded the tool
and were removed. New UI must not compromise the search -> snapshot ->
workbook flow.

## Claude Review Guide

Recommended review order:

1. `README.md` - mission, history, decisions, and roadmap.
2. `app.py` - search flow, cache behavior, coverage UI, and output contract.
3. `sec_filings.py` - SEC retrieval, statuses, event retention, enrichment, and
   snapshot derivation.
4. `sec_parsers.py` - fixture-backed extraction heuristics, including the
   narrow Increment 9 quoted-prose ticker case.
5. `readiness.py` - launch-candidate and effective-amendment state machine.
6. `theme_classifier.py` and `config.py` - classification terms and filer/ticker
   configuration.
7. `tests/` - protected behavior and acceptance evidence.
8. `git log --oneline` - commit-by-commit implementation history.

Review questions:

1. Do commits `8f5d6c5` through `6ce3c3f` satisfy Increments 1-8.5 exactly?
2. Are filing events still retained while the primary output remains one latest
   amendment-aware row per fund?
3. Are cache, partial-failure, enrichment, ticker, placeholder, and readiness
   behaviors adequately protected by tests?
4. Does Increment 9 preserve the approved identity, vehicle, cache, and
   readiness contracts while resolving only the documented cleanup items?
5. Are there any regressions, hidden coupling, or missing fixtures that should
   block the next increment?
