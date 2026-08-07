# ETF Dash — Project Context (LLM ingest / integration spec)

This document is a self-contained technical specification of **ETF Dash**, written so
another LLM or engineer can understand the project completely and integrate, extend, or
re-build it — including on a non-Streamlit UI — without needing the GitHub repository.
It is comprehensive by design. Companion docs: `README.md` (product-facing) and
`HANDOFF.md` (increment-by-increment implementation history).

Live app: https://etfdash.streamlit.app/ · Repository (public): https://github.com/halestorm9352/ETF-Dashboard

---

## 1. What ETF Dash is (and is not)

ETF Dash is a **primary-source SEC-filing radar for NEW ETF registrations and launches,
before they list on an exchange**, organized by the **legal filer / registrant / series
trust**. It converts SEC registration filings (S-1, N-1A, 485APOS, 485BPOS) into a live,
amendment-aware snapshot of the **forward launch pipeline**, with effectiveness timing,
SEC series/class identity, vehicle classification, ticker development, theme, and
launch-readiness state, plus a review-ready Excel export.

It is **NOT** a price dashboard, a portfolio/holdings tracker, an ML price forecaster, or
an existing-fund screener. Its differentiator is *pre-launch* intelligence from *primary*
filings — a niche that is largely unoccupied. Everything is sourced from SEC EDGAR; there
is no scraping of third-party sites (ETF.com/ETFdb and news rails were explicitly removed).

**Organizing perspective:** the legal filer/registrant/series trust — because that lens is
what matters for service-provider analysis (custody, fund administration, transfer agency).
Consumer brand names are competitive signals, not the primary identity model.

## 2. Core capability and output

Pipeline: search SEC filings by legal filer (CIK) and date range → retain every detected
filing **event** as immutable source history → derive **one latest, amendment-aware
snapshot row per fund identity** → enrich with effectiveness timing, ticker status,
vehicle, theme, and launch readiness → present a table + one Excel workbook + a
launch-pipeline brief.

**Core invariant:** filing events are kept as source history; the product presents one
latest amendment-aware snapshot row per fund identity.

## 3. Domain primer (SEC ETF registration mechanics)

An LLM integrating this must understand the filing mechanics it encodes:

- **Registrants file with the SEC via EDGAR.** Each filer has a **CIK** (Central Index
  Key). A trust/registrant contains **series** (`series_id`, e.g. `S000109282`), and each
  series contains **classes** (`class_id`, e.g. `C000280390`). An ETF is typically a
  standalone class; a mutual fund has multiple share classes under one series.
- **Tracked forms** (`config.FORMS`): `S-1`, `N-1A` (initial registrations), `485APOS`
  (post-effective amendment filed under Rule 485(a) — becomes effective after a delay),
  `485BPOS` (post-effective amendment filed under Rule 485(b) — typically immediately or
  designated-date effective).
- **Rule 485 effectiveness timing** (the key "when does it launch" signal):
  - Immediate upon filing (Rule 485(b)) → effective on the filing date.
  - 60 days after filing (Rule 485(a)(1)).
  - 75 days after filing (Rule 485(a)(2)).
  - A designated effective date under Rule 485(a) or 485(b).
  A fund is legally able to trade only once its registration is effective; actual exchange
  listing usually lags effectiveness by days–weeks (see limitation on Form 8-A below).
- **The SEC fund-ticker map** (`company_tickers_mf.json`) provides authoritative
  CIK+series+class → ticker joins.

## 4. Identity model (the snapshot identity)

Snapshot identity precedence:
```
(CIK, series_id, class_id)   → standalone ETF classes
(CIK, series_id)             → parent-scoped mutual-fund classes
(CIK, normalized fund name)  → only when SEC IDs are absent
```
Identity scope is stabilized per class across its filing history. Filing events remain
separate evidence even when several class rows roll up to one parent-series snapshot.

**Dual-vehicle series** (intentional two rows, not a duplicate): a series holding both an
ETF class and mutual-fund classes yields (a) the ETF class as a standalone identity, and
(b) the mutual-fund classes rolled up under the parent series — two vehicle signals in one
legal series.

## 5. Data model

### 5.1 Filing event (source history)
One filing occurrence for one detected fund. Persisted fields (`store.EVENT_FIELDS`):
```
event_id, accession_number, cik, form, date, accepted_at,
etf_name, class_name, series_name, series_id, class_id,
ticker, ticker_at_filing, ticker_source,
vehicle, identity_scope, filer, link,
effectiveness_basis, effectiveness_days, designated_effective_date, effectiveness_label
```
Notes:
- `event_id` = `"{accession_number}:{identity_token}"` where identity_token is
  class_id, else series_id, else normalized name.
- `ticker_at_filing` is **immutable evidence**; `ticker` is the enriched/current value.
  `ticker_source` records provenance (`filing`, `sec_fund_ticker_map`, later-filing
  fallback).
- `effectiveness_basis` ∈ {`""`, `rule_485_b_immediate`, `rule_485_a1_60_days`,
  `rule_485_a2_75_days`, `rule_485_b_designated_date`, `rule_485_a_designated_date`}.
  `effectiveness_days` is 0/60/75/None; `designated_effective_date` is a date string or "".
- `vehicle` ∈ {`ETF`, `Mutual fund share class`, `Other / unknown`}.

### 5.2 Snapshot row (read-time derived)
`derive_latest_fund_rows()` keeps the newest event per identity and adds
`filing_event_count`, `amendment_count`, `filing_form_history`. `add_launch_readiness_columns()`
then adds derived columns (NOT stored): `filing_stage`, `earliest_auto_effective_date`,
`launch_readiness`, `needs_ticker` (bool), `etf_share_class` (bool), `days_to_readiness`.

## 6. Persistent store (the portable integration artifact)

The product is **store-first**. A committed SQLite file `data/etf_dash.sqlite` is the
portable artifact; the repository is only its transport. `store.py` is the **UI-agnostic,
standard-library-only** access boundary (no Streamlit, no third-party imports) — it is the
intended integration seam.

`SCHEMA_VERSION = 1`. Five tables:

| Table | Purpose / key fields |
|---|---|
| `store_meta` | key/value: `schema_version`, `backfill_floor` (trailing-365-day), `created_at`. |
| `filing_events` | source events keyed by `event_id`; the 22 `EVENT_FIELDS` above + `ingested_at`, `parser_version`. Indexed on `(cik,date)`, `series_id`, `accession_number`. Snapshot-derived fields are NOT stored. |
| `processed_filings` | accession-level ledger keyed by `accession_number`: cik, form, filing_date, `parser_version`, event_count, ingested_at. |
| `series_registry` | immutable first-filing dates keyed by `series_id`: cik, first_filing_date, lookup_source, resolved_at. |
| `ingest_runs` | audit per run: mode, bounds, ciks_attempted/failed, filings_processed, events_added, timestamps, error_summary. |

`store.load_events(handle, start_date, end_date, ciks=None)` returns event dicts in the
same shape `sec_filings.fetch_filing_events()` produces, so persisted and live events flow
through identical enrichment/snapshot code.

Approx. current size: ~5,700 events / ~1,260 accessions / ~4,000 series, trailing 12 months.

## 7. Architecture and data flow

```
Scheduled GitHub Actions ingest (~7:00 & 16:00 America/New_York)
  -> configured SEC CIK universe (config.CIKS, ~45)
  -> SEC submissions JSON, filing indexes, bounded primary documents
  -> parse events + Rule 485 effectiveness + SEC ticker-map enrichment
  -> upsert into data/etf_dash.sqlite; commit the store (+ launch brief) when it changes

Streamlit app (store-first read path, app_data.py)
  -> load events for selected CIKs/dates from the store
  -> live SEC "top-up" only for the gap beyond the last ingest (3-day overlap)
  -> merge stored+live by event_id (live wins overlap) -> common finalization
  -> SEC ticker-map enrichment + bounded ID-less fallback
  -> vehicle classification + identity-scope stabilization
  -> latest row per identity (+ amendment history)
  -> timing-first readiness + theme + etf_share_class
  -> toggle-controlled table + Excel workbook + read-only launch-brief panel
```

A covering store produces **zero network calls**. Missing/empty store → pure-live
fallback. Failed top-up → stored snapshot with a non-fatal warning. The Streamlit-free
layer (`store.py`, `app_data.py`, `sec_filings.py`, `readiness.py`, `vehicle_classifier.py`,
`sec_parsers.py`, `theme_classifier.py`, `config.py`) means a non-Streamlit UI can reuse
the entire pipeline unchanged.

## 8. Module / function surface (programmatic API)

All modules below are importable and Streamlit-free (only `app.py` imports Streamlit).

- **`store.py`** — SQLite boundary. `open_store(path)`, `upsert_events(handle, events,
  parser_version)`, `load_events(handle, start, end, ciks=None)`,
  `record_processed_filing(...)`, `is_filing_processed(handle, accession)`,
  `processed_filing_parser_version(handle, accession)`, `get_series_registry(handle)`,
  `upsert_series_registration(...)`, `record_ingest_run(handle, run)`,
  `get_last_successful_ingest(handle)`. Constants `SCHEMA_VERSION`, `EVENT_FIELDS`.
- **`sec_filings.py`** — retrieval + snapshot. `fetch_filing_events(start,end,ciks)` (live),
  `finalize_event_rows(rows,start,end,ticker_mapping=None)` (enrich+filter+sort — shared by
  live and store paths), `derive_latest_fund_rows(rows)` (snapshot),
  `fetch_series_registration_date(series_id)`, `normalize_event_ticker(row)`.
  Constant `MODULE_CONTRACT_VERSION`.
- **`app_data.py`** — store-first runtime (Streamlit-free).
  `load_store_first_filing_events(store_path, start, end, ciks, live_fetch=...)`,
  `load_store_series_registry(store_path)`,
  `resolve_series_registration_status(series_id, registry, live_fetch=...)`,
  `load_launch_brief(brief_path) -> dict|None`.
- **`readiness.py`** — launch-readiness state machine.
  `add_launch_readiness_columns(df, series_first_filing_dates=None, search_start_date=None,
  series_new_months=18, today=None)`, `readiness_status(row, today)`,
  `series_ids_requiring_age_lookup(df)`. Sets: `DEFAULT_VISIBLE_STATUSES`,
  `HIDDEN_BY_DEFAULT_STATUSES`; state-name constants.
- **`vehicle_classifier.py`** — `classify_vehicle(row)`, `is_share_class_name(v)`,
  `is_mutual_fund_ticker(v)`, `uses_parent_series_identity(row)`; constants `ETF_VEHICLE`,
  `MUTUAL_FUND_SHARE_CLASS`, `UNKNOWN_VEHICLE`.
- **`sec_parsers.py`** — extraction heuristics.
  `extract_rule_485_effectiveness(text)`, `detect_exchange_listed(text)`,
  `extract_series_entries(text)`, `extract_named_ticker_pairs(text)`,
  `extract_ticker(text, ...)`, `extract_etf_name(text)`, `extract_filer_name(text)`,
  `classify_vehicle` (re-export), `sanitize_ticker(t)`. Constants `PARSER_VERSION`,
  `MODULE_CONTRACT_VERSION`, effectiveness window sizes.
- **`theme_classifier.py`** — `classify_primary_theme(name)`, `summarize_themes(rows)`,
  `THEME_ORDER`.
- **`config.py`** — `CIK_LOOKUP` (~45 CIK→name), `CIKS`, `CIK_GROUP_OPTIONS`, segments,
  `FORMS`, `DATA_VERSION`, `SEC_MAX_WORKERS`, `INDEX_PAGE_MAX_CHARS` (300k),
  `PRIMARY_DOCUMENT_MAX_CHARS` (1,000,000), `PRIMARY_IDENTITY_MAX_CHARS` (300k),
  `SERIES_NEW_MONTHS` (18), SEC HTTP headers/User-Agent.
- **`scripts/ingest_filings.py`** — CLI: `--backfill` (trailing 365d), `--incremental`
  (from last end bound − 3d overlap), `--backfill --days N` (windowed), `--store PATH`.
- **`scripts/generate_launch_brief.py`** — builds the deterministic launch brief JSON.

Minimal headless consumption example (no Streamlit):
```python
from datetime import date
from store import open_store, load_events, get_series_registry
from sec_filings import finalize_event_rows, derive_latest_fund_rows
from readiness import add_launch_readiness_columns, DEFAULT_VISIBLE_STATUSES
import pandas as pd

h = open_store("data/etf_dash.sqlite")
rows = load_events(h, date(2026,1,1), date(2026,12,31))           # or ciks=[...]
registry = get_series_registry(h); h.close()
final = finalize_event_rows([dict(r) for r in rows], date(2026,1,1), date(2026,12,31))
snap = pd.DataFrame(derive_latest_fund_rows(final))
snap["date"] = pd.to_datetime(snap["date"], errors="coerce")
snap = add_launch_readiness_columns(snap, series_first_filing_dates=registry,
                                    search_start_date=date(2026,1,1), today=date.today())
forward = snap[snap["launch_readiness"].isin(DEFAULT_VISIBLE_STATUSES)]   # not-yet-listed pipeline
```

## 9. Launch-readiness taxonomy

Timing is the **primary** axis; ticker presence is an orthogonal boolean `needs_ticker`
(not a state). Eight states:

| State | Meaning |
|---|---|
| `Initial review` | S-1 / N-1A initial registration. |
| `Upcoming launch` | new-pipeline ETF, **future** effective date, no prior effectiveness. |
| `Recently launched` | new-pipeline ETF, effective today or within the prior 30 days. |
| `Launched (stale)` | new-pipeline ETF, effective > 30 days ago. |
| `Existing fund amendment` | pipeline-looking filing overridden by prior effectiveness OR a series first registered > 18 months before the search start. |
| `Routine 485(b) update` | already-effective history of only 485BPOS filings. |
| `Effective (amendment)` | other already-effective amendment history. |
| `Timing undetected` | no supported effectiveness election/date parsed. |

**Default view = not-yet-effective only:** `DEFAULT_VISIBLE_STATUSES = {Initial review,
Upcoming launch}`. Everything already-effective/routine/undetected is hidden behind a
toggle. "New = not yet listed on an exchange" is the product's core stance; not-yet-effective
is the proxy (Form 8-A listing detection is a deferred precision upgrade).

Orthogonal flags: `needs_ticker` (no assigned ticker yet); `etf_share_class` (an ETF row
whose series also has a mutual-fund-share-class sibling in the same snapshot — a
multi-share-class ETF structure; V1 requires both siblings in-window).

## 10. Vehicle classification (`classify_vehicle`)

Precedence: 5-letter `X` ticker or explicit share-class name → `Mutual fund share class`;
"ETF" in name or Bull/Bear `nX Shares` or a 1–4 letter ticker → `ETF`; an
exchange-listing evidence flag (`detect_exchange_listed`, from the primary-document front
matter) rescues tickerless "…Fund" ETFs → `ETF`; otherwise `Other / unknown`. Read-time
normalization never downgrades a recognized stored vehicle to unknown (preserves the
parse-time exchange-listing classification).

## 11. Rule 485 effectiveness parsing (`extract_rule_485_effectiveness`)

Reads the facing-sheet effectiveness election from the primary document. Locates the
anchor "it is proposed that this filing will become effective" (or a paragraph fallback)
scanning up to 1,000,000 chars, then parses a bounded window: detects immediate /
60-day / 75-day / designated-date elections from checked table rows OR inline
checkbox glyphs (`☑/☒/■/●`, Wingdings `þ`), selecting the option whose nearest preceding
marker is checked. **Identity/named-pair extraction is separately bounded to the first
300k chars** (`PRIMARY_IDENTITY_MAX_CHARS`) to avoid scraping exhibit lists (sub-advisory
agreements, Schedule A) as if they were funds — effectiveness gets the deep window,
identity stays in the front matter.

## 12. Theme classification

`classify_primary_theme(name)` is rule-based over the fund name. Themes include
`Leveraged / Inverse`, `Options Income / Covered Call`, `Thematic Equity`,
`Fixed Income / Credit`, `Crypto / Digital Assets`, `Target Maturity`,
`Factor / Quant / Active`, `International / Emerging Markets`, `Dividend / Income`,
`Commodities / Gold / Energy`, `Other`. Coverage of `Other` is a known gap.

## 13. Versioning and reprocessing

- `SCHEMA_VERSION = 1` (store schema).
- `MODULE_CONTRACT_VERSION = 12` (app↔parser/filings module compatibility guard).
- `PARSER_VERSION = 15` (dedicated parser stamp; bumped whenever parsed event VALUES
  change — parser logic, fetch reach, or parse-time enrichment). Stamped on `filing_events`
  and `processed_filings`. The ingest **reprocesses** any accession whose stored
  `parser_version` < current, so a parser improvement self-propagates: on the next scheduled
  run (or a windowed `--backfill --days N`) stale rows are re-fetched and re-parsed in place.
  Event IDs are identity-derived (stable across value-only parser changes).
- `DATA_VERSION = "2026-07-20-increment-12-new-fund-scope-v8"` (Streamlit cache key).

## 14. Launch brief

`scripts/generate_launch_brief.py` deterministically writes `data/launch_brief.json`
(no LLM, no network) from the store: a compact snapshot of the not-yet-effective pipeline
— `as_of`, `total`, `upcoming`, `initial_review`, and top-8 `top_filers` / `top_themes`.
The scheduled ingest regenerates and commits it when the store changes; the app renders it
read-only (Top Filers | Top Themes side by side).

## 15. Configuration

The CIK universe (~45 issuers) is maintained manually in `config.py` (no auto-discovery),
grouped into segments (`All`, `Top 3`, `The Field`, `Series Trusts`). The date picker is
restricted to the current calendar year; the store serves speed, series ages, and history.
SEC access is behind a shared limiter (~8 requests/sec) with 403/429 retry.

## 16. Integration guidance

Intended integration: combine ETF Dash's **pre-launch/new-fund pipeline + legal-filer &
service-provider lens** with a large dataset of **existing public funds by asset manager /
service provider**. Guidance:

- **Consume the store, not the UI.** Treat `data/etf_dash.sqlite` (via `store.py`) as the
  interface. Its schema is stable (`SCHEMA_VERSION`), UI-agnostic, and standard-library-only.
  Join your existing-funds dataset to ETF Dash on **SEC identity** (`cik`, `series_id`,
  `class_id`) and/or `ticker`; fall back to normalized fund name only when SEC IDs are absent.
- **The value ETF Dash adds** to an existing-funds corpus: (1) the *forward* pipeline (funds
  not yet listed), which by definition is absent from any "existing funds" dataset; (2)
  effectiveness timing (when a fund can launch); (3) the legal-registrant/series-trust
  structure that maps to service-provider relationships; (4) amendment history and
  launch-readiness state; (5) vehicle and ETF-share-class signals.
- **Service-provider angle:** the registrant/series-trust identity is the join key to
  custody/administration/transfer-agency relationships. ETF Dash organizes by legal filer
  precisely so this join is clean; a brand-organized dataset should be reconciled to CIK.
- **To reproduce data for other issuers**, add their CIKs to `config.CIK_LOOKUP` and run
  `python scripts/ingest_filings.py --backfill`. No third-party data sources are required or
  used; everything derives from SEC EDGAR.
- **To port off Streamlit:** reuse the Streamlit-free layer verbatim; only `app.py` (UI) is
  Streamlit-specific. Reads go through `app_data.load_store_first_filing_events(...)` with a
  `live_fetch` callable (pass `sec_filings.fetch_filing_events`) for the top-up, then
  `derive_latest_fund_rows` + `add_launch_readiness_columns`. The Excel workbook and the
  launch brief are both derivable from the same snapshot dataframe.

## 17. Limitations (known, current)

1. Rows without SEC series/class IDs use normalized-name fallback identity.
2. Date picker limited to the current calendar year; store top-up extends only the trailing
   edge (prior-year support would need a floor-side top-up).
3. SEC layouts are heuristic; some non-standard 485 filings remain `Timing undetected`.
4. `etf_share_class` requires both sibling vehicles in the selected window.
5. Mutual-fund→ETF conversions are not yet detected (would need N-14/proxy forms or
   conversion-language parsing).
6. Store-first reads rely on ingest-time SEC ticker mapping; a ticker missed during a
   mapping outage does not self-heal at read time.
7. Filer universe is manually maintained.
8. No dedicated vehicle filter in the current UI.
9. "Not yet listed" is proxied by "not yet effective"; a small effective-but-not-yet-trading
   window is not distinguished (Form 8-A listing detection is the deferred precision fix).

## 18. Deferred roadmap

Mutual-fund→ETF conversion detection; issuer net flows from primary sources (N-PORT-derived
shares outstanding × NAV, ~60-day lag disclosed); aggregate AUM growth; Form 8-A listing
precision; broader theme coverage. Filer-focused news is on hold indefinitely (prior rails
crowded the tool without decision value).

## 19. Run / rebuild reference

Runtime: Python 3.14. Dependencies (`requirements.txt`, bounded below next major):
`requests`, `beautifulsoup4`, `openpyxl`, `streamlit` (UI only), `pandas`.

```
python -m venv .venv && .venv/Scripts/activate      # Windows; use bin/activate on POSIX
pip install -r requirements.txt
streamlit run app.py                                 # the Streamlit UI
python scripts/ingest_filings.py --incremental       # refresh the store
python scripts/generate_launch_brief.py              # regenerate the brief JSON
python -m unittest discover -s tests                 # full test suite
```

Entry points: `app.py` (UI), `scripts/ingest_filings.py` (data pipeline),
`scripts/generate_launch_brief.py` (brief), `store.py` (data interface). Everything except
`app.py` is UI-agnostic and reusable.
