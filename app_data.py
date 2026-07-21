from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

from config import CIK_LOOKUP
from sec_filings import FilingEventResults, finalize_event_rows
from store import get_last_successful_ingest, get_series_registry, load_events, open_store


def _store_is_available(store_path: Path) -> bool:
    try:
        return store_path.is_file() and store_path.stat().st_size > 0
    except OSError:
        return False


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _status_for_cik(
    cik: str,
    rows: list[dict[str, Any]],
    *,
    source: str,
    success: bool = True,
    error_summary: str = "",
) -> dict[str, Any]:
    return {
        "cik": cik,
        "filer": CIK_LOOKUP.get(cik, cik),
        "status": "success" if success else "failed",
        "success": success,
        "failed": not success,
        "row_count": sum(str(row.get("cik", "")) == cik for row in rows),
        "error_summary": error_summary,
        "source": source,
    }


def _merge_by_event_id(
    stored_rows: Iterable[dict[str, Any]],
    live_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    unkeyed: list[dict[str, Any]] = []
    for row in (*stored_rows, *live_rows):
        event_id = str(row.get("event_id", "") or "").strip()
        if event_id:
            merged[event_id] = dict(row)
        else:
            unkeyed.append(dict(row))
    return [*merged.values(), *unkeyed]


def load_store_first_filing_events(
    store_path,
    start_date,
    end_date,
    selected_ciks,
    *,
    live_fetch: Callable[..., Any],
) -> tuple[FilingEventResults, list[dict[str, str]]]:
    path = Path(store_path)
    ciks = tuple(str(cik) for cik in selected_ciks)
    if not _store_is_available(path):
        return live_fetch(start_date, end_date, ciks=ciks), []

    notices: list[dict[str, str]] = []
    try:
        handle = open_store(path)
        try:
            stored_rows = load_events(handle, start_date, end_date, ciks=ciks)
            last_ingest = get_last_successful_ingest(handle)
        finally:
            handle.close()
    except Exception as exc:
        notices.append(
            {
                "level": "warning",
                "message": (
                    "The local filing store could not be read; using live SEC data. "
                    f"({type(exc).__name__})"
                ),
            }
        )
        return live_fetch(start_date, end_date, ciks=ciks), notices

    requested_end = _date_value(end_date)
    stored_end = (
        _date_value(last_ingest["end_bound"])
        if last_ingest and last_ingest.get("end_bound")
        else None
    )
    live_rows: list[dict[str, Any]] = []
    live_statuses_by_cik: dict[str, dict[str, Any]] = {}
    mapping_status = {
        "available": True,
        "error_summary": "",
        "source": "store",
    }
    top_up_attempted = stored_end is None or requested_end > stored_end
    top_up_error = ""

    if top_up_attempted:
        gap_start = (
            stored_end - timedelta(days=3)
            if stored_end is not None
            else _date_value(start_date)
        )
        try:
            top_up = live_fetch(gap_start, end_date, ciks=ciks)
            live_rows = list(top_up)
            live_statuses_by_cik = {
                str(status.get("cik", "")): dict(status)
                for status in getattr(top_up, "statuses", [])
            }
            mapping_status = dict(
                getattr(
                    top_up,
                    "mapping_status",
                    {"available": True, "error_summary": ""},
                )
            )
            failed_top_up = [
                status
                for status in live_statuses_by_cik.values()
                if not status.get("success", False)
            ]
            if failed_top_up:
                top_up_error = "Live SEC top-up was incomplete for one or more filers."
        except Exception as exc:
            top_up_error = f"{type(exc).__name__}: {exc}"

        if top_up_error:
            notices.append(
                {
                    "level": "warning",
                    "message": (
                        "Live SEC top-up is temporarily unavailable; showing stored "
                        f"coverage only. {top_up_error}"
                    ),
                }
            )

    merged_rows = _merge_by_event_id(stored_rows, live_rows)
    finalized_rows = finalize_event_rows(merged_rows, start_date, end_date)
    statuses: list[dict[str, Any]] = []
    for cik in ciks:
        live_status = live_statuses_by_cik.get(cik)
        if live_status and not live_status.get("success", False):
            statuses.append(
                _status_for_cik(
                    cik,
                    finalized_rows,
                    source="store+live",
                    success=False,
                    error_summary=str(live_status.get("error_summary", "Top-up failed")),
                )
            )
        elif top_up_attempted and top_up_error and not live_status:
            statuses.append(
                _status_for_cik(
                    cik,
                    finalized_rows,
                    source="store",
                    success=False,
                    error_summary=top_up_error,
                )
            )
        else:
            statuses.append(
                _status_for_cik(
                    cik,
                    finalized_rows,
                    source="store+live" if top_up_attempted else "store",
                )
            )

    return FilingEventResults(finalized_rows, statuses, mapping_status), notices


def load_store_series_registry(store_path) -> dict[str, str]:
    path = Path(store_path)
    if not _store_is_available(path):
        return {}
    try:
        handle = open_store(path)
        try:
            registry = get_series_registry(handle)
        finally:
            handle.close()
    except Exception:
        return {}
    return {
        str(series_id).strip().upper(): first_filing_date
        for series_id, first_filing_date in registry.items()
    }


def resolve_series_registration_status(
    series_id,
    series_registry,
    *,
    live_fetch: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    normalized_series_id = str(series_id or "").strip().upper()
    first_filing_date = series_registry.get(normalized_series_id, "")
    if first_filing_date:
        return {
            "series_id": normalized_series_id,
            "success": True,
            "first_filing_date": first_filing_date,
            "error_summary": "",
        }
    try:
        return dict(live_fetch(normalized_series_id))
    except Exception as exc:
        return {
            "series_id": normalized_series_id,
            "success": False,
            "first_filing_date": "",
            "error_summary": f"{type(exc).__name__}: {exc}",
        }
