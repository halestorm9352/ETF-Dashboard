from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import CIKS, SEC_MAX_WORKERS
from sec_filings import (
    _fetch_filings_for_cik,
    fetch_sec_fund_ticker_mapping,
    fetch_series_registration_date,
)
from sec_parsers import PARSER_VERSION
from store import (
    get_last_successful_ingest,
    open_store,
    processed_filing_parser_version,
    record_ingest_run,
    record_processed_filing,
    upsert_events,
    upsert_series_registration,
)


DEFAULT_STORE_PATH = PROJECT_ROOT / "data" / "etf_dash.sqlite"
BACKFILL_DAYS = 365
INCREMENTAL_OVERLAP_DAYS = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _ingest_bounds(
    handle,
    mode: str,
    today: date,
    backfill_days: int | None = None,
) -> tuple[date, date]:
    if mode == "backfill":
        days = backfill_days if backfill_days is not None else BACKFILL_DAYS
        return today - timedelta(days=days), today
    last_run = get_last_successful_ingest(handle)
    if last_run:
        return (
            _parse_date(last_run["end_bound"])
            - timedelta(days=INCREMENTAL_OVERLAP_DAYS),
            today,
        )
    return today - timedelta(days=BACKFILL_DAYS), today


def _unresolved_series(handle) -> list[tuple[str, str]]:
    return [
        (row["series_id"], row["cik"])
        for row in handle.execute(
            """
            SELECT DISTINCT filing_events.series_id, filing_events.cik
            FROM filing_events
            LEFT JOIN series_registry
              ON series_registry.series_id = filing_events.series_id
            WHERE filing_events.series_id != ''
              AND series_registry.series_id IS NULL
            ORDER BY filing_events.series_id
            """
        )
    ]


def run_ingest(
    handle,
    *,
    mode: str,
    ciks: Iterable[str],
    today: date | None = None,
    backfill_days: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if mode not in {"backfill", "incremental"}:
        raise ValueError("Ingest mode must be 'backfill' or 'incremental'.")
    run_today = today or date.today()
    selected_ciks = [str(cik) for cik in ciks]
    start_bound, end_bound = _ingest_bounds(
        handle,
        mode,
        run_today,
        backfill_days=backfill_days,
    )
    started_at = _utc_now()
    ticker_mapping = fetch_sec_fund_ticker_mapping()

    statuses: list[dict[str, Any]] = []
    filings_processed = 0
    filings_reprocessed = 0
    filings_skipped = 0
    events_added = 0
    events_updated = 0
    ciks_completed = 0

    def fetch_cik(cik: str):
        return _fetch_filings_for_cik(
            cik,
            datetime.combine(start_bound, datetime.min.time()),
            datetime.combine(end_bound, datetime.max.time()),
            primary_document_workers=1,
            ticker_mapping=ticker_mapping,
        )

    def store_cik_result(cik: str, rows, status) -> None:
        nonlocal ciks_completed, filings_processed, filings_reprocessed
        nonlocal filings_skipped
        nonlocal events_added, events_updated
        statuses.append(status)
        ciks_completed += 1
        if progress:
            progress(
                f"CIKs completed: {ciks_completed}/{len(selected_ciks)} "
                f"({status.get('status', 'unknown')}: {cik})"
            )
        if not status.get("success"):
            return

        rows_by_accession: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            rows_by_accession[str(row.get("accession_number", "") or "")].append(row)
        for accession, filing_events in rows_by_accession.items():
            if not accession:
                continue
            stored_parser_version = processed_filing_parser_version(
                handle,
                accession,
            )
            if (
                stored_parser_version is not None
                and stored_parser_version >= PARSER_VERSION
            ):
                filings_skipped += 1
                continue
            # Event IDs are stable for this value-only parser change. A future
            # identity change would also need orphan-event cleanup.
            counts = upsert_events(
                handle,
                filing_events,
                parser_version=PARSER_VERSION,
            )
            first_event = filing_events[0]
            record_processed_filing(
                handle,
                accession,
                first_event.get("cik", cik),
                first_event.get("form", ""),
                first_event.get("date", ""),
                PARSER_VERSION,
                len(filing_events),
            )
            filings_processed += 1
            if stored_parser_version is not None:
                filings_reprocessed += 1
            events_added += counts["events_added"]
            events_updated += counts["events_updated"]

    cik_worker_count = max(1, min(SEC_MAX_WORKERS, len(selected_ciks)))
    if cik_worker_count == 1:
        for cik in selected_ciks:
            rows, status = fetch_cik(cik)
            store_cik_result(cik, rows, status)
    else:
        with ThreadPoolExecutor(max_workers=cik_worker_count) as executor:
            future_map = {executor.submit(fetch_cik, cik): cik for cik in selected_ciks}
            for future in as_completed(future_map):
                cik = future_map[future]
                try:
                    rows, status = future.result()
                except Exception as exc:
                    rows = []
                    status = {
                        "cik": cik,
                        "filer": cik,
                        "status": "failed",
                        "success": False,
                        "failed": True,
                        "row_count": 0,
                        "error_summary": f"{type(exc).__name__}: {exc}",
                    }
                store_cik_result(cik, rows, status)

    series_resolved = 0
    series_checked = 0
    series_unresolved: list[dict[str, str]] = []
    unresolved_series = _unresolved_series(handle)
    if progress:
        progress(f"Series registration lookups required: {len(unresolved_series)}")

    def store_series_result(series_id: str, cik: str, status) -> None:
        nonlocal series_checked, series_resolved
        series_checked += 1
        if status.get("success") and status.get("first_filing_date"):
            upsert_series_registration(
                handle,
                series_id,
                cik,
                status["first_filing_date"],
                "sec_browse_edgar_atom",
            )
            series_resolved += 1
        else:
            series_unresolved.append(
                {
                    "series_id": series_id,
                    "error_summary": str(status.get("error_summary", "Lookup failed")),
                }
            )
        if progress and (
            series_checked == len(unresolved_series) or series_checked % 100 == 0
        ):
            progress(
                f"Series checked: {series_checked}/{len(unresolved_series)}; "
                f"resolved: {series_resolved}"
            )

    series_worker_count = max(1, min(SEC_MAX_WORKERS, len(unresolved_series)))
    if series_worker_count == 1:
        for series_id, cik in unresolved_series:
            store_series_result(
                series_id,
                cik,
                fetch_series_registration_date(series_id),
            )
    else:
        with ThreadPoolExecutor(max_workers=series_worker_count) as executor:
            future_map = {
                executor.submit(fetch_series_registration_date, series_id): (series_id, cik)
                for series_id, cik in unresolved_series
            }
            for future in as_completed(future_map):
                series_id, cik = future_map[future]
                try:
                    status = future.result()
                except Exception as exc:
                    status = {
                        "series_id": series_id,
                        "success": False,
                        "first_filing_date": "",
                        "error_summary": f"{type(exc).__name__}: {exc}",
                    }
                store_series_result(series_id, cik, status)

    failed_statuses = [status for status in statuses if not status.get("success")]
    errors = [
        f"{status.get('filer', status.get('cik', 'Unknown filer'))}: "
        f"{status.get('error_summary', 'Fetch failed')}"
        for status in failed_statuses
    ]
    if not getattr(ticker_mapping, "available", True):
        errors.append(
            "SEC ticker mapping unavailable: "
            f"{getattr(ticker_mapping, 'error_summary', 'fetch failed')}"
        )
    if series_unresolved:
        errors.append(
            "Unresolved series: "
            + ", ".join(item["series_id"] for item in series_unresolved)
        )

    completed_at = _utc_now()
    run_record = {
        "mode": mode,
        "started_at": started_at,
        "completed_at": completed_at,
        "start_bound": start_bound.isoformat(),
        "end_bound": end_bound.isoformat(),
        "ciks_attempted": len(selected_ciks),
        "ciks_failed": len(failed_statuses),
        "filings_processed": filings_processed,
        "events_added": events_added,
        "error_summary": "\n".join(errors),
    }
    run_id = record_ingest_run(handle, run_record)
    handle.commit()
    handle.execute("VACUUM")

    all_ciks_failed = bool(selected_ciks) and len(failed_statuses) == len(selected_ciks)
    return {
        **run_record,
        "run_id": run_id,
        "filings_skipped": filings_skipped,
        "filings_reprocessed": filings_reprocessed,
        "events_updated": events_updated,
        "series_resolved": series_resolved,
        "series_unresolved": series_unresolved,
        "statuses": statuses,
        "exit_code": 1 if all_ciks_failed else 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest SEC ETF filing events.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true")
    mode.add_argument("--incremental", action="store_true")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE_PATH)
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Override the backfill window in days; ignored for incremental runs.",
    )
    return parser


def main(argv=None, *, ciks=None, today=None) -> int:
    args = build_parser().parse_args(argv)
    mode = "backfill" if args.backfill else "incremental"
    handle = open_store(args.store)
    try:
        result = run_ingest(
            handle,
            mode=mode,
            ciks=CIKS if ciks is None else ciks,
            today=today,
            backfill_days=args.days,
            progress=lambda message: print(message, file=sys.stderr, flush=True),
        )
    finally:
        handle.close()
    print(json.dumps(result, indent=2, default=str))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
