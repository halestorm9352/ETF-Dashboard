from __future__ import annotations

import csv
from datetime import date, datetime
from io import StringIO
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from config import CIKS
from readiness import add_launch_readiness_columns
from sec_filings import (
    derive_latest_fund_rows,
    finalize_event_rows,
    normalize_event_ticker,
)
from store import EVENT_FIELDS, get_series_registry, load_events, open_store
from theme_classifier import classify_primary_theme


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
    return date.fromisoformat(str(value)[:10])


def read_store_bytes(store_path) -> bytes | None:
    path = Path(store_path)
    try:
        return path.read_bytes() if path.is_file() else None
    except OSError:
        return None


def export_events_csv(store_path) -> bytes | None:
    path = Path(store_path)
    if not _store_is_available(path):
        return None

    try:
        handle = open_store(path)
        try:
            rows = handle.execute(
                f"SELECT {', '.join(EVENT_FIELDS)} FROM filing_events "
                "ORDER BY date DESC, accepted_at DESC, event_id"
            ).fetchall()
        finally:
            handle.close()
    except (OSError, sqlite3.Error):
        return None

    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    # Feed rows separately so EVENT_FIELDS remains the authoritative column order.
    writer.writerow(EVENT_FIELDS)
    for row in rows:
        writer.writerow(
            ["" if row[field] is None else row[field] for field in EVENT_FIELDS]
        )
    return output.getvalue().encode("utf-8")


def export_snapshot_csv(store_path, today=None) -> bytes | None:
    path = Path(store_path)
    if not _store_is_available(path):
        return None

    as_of = _date_value(today or date.today())
    start_date = date(as_of.year, 1, 1)
    try:
        handle = open_store(path)
        try:
            events = load_events(handle, start_date, as_of, ciks=CIKS)
            series_registry = get_series_registry(handle)
        finally:
            handle.close()
    except (OSError, sqlite3.Error):
        return None

    if not events:
        return None

    snapshot_rows = derive_latest_fund_rows(
        finalize_event_rows(events, start_date, as_of)
    )
    if not snapshot_rows:
        return None

    frame = pd.DataFrame(snapshot_rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).copy()
    if frame.empty:
        return None

    frame["ticker"] = frame.apply(
        lambda row: normalize_event_ticker(row.to_dict()),
        axis=1,
    )
    frame["themes"] = frame["etf_name"].apply(classify_primary_theme)
    frame = add_launch_readiness_columns(
        frame,
        series_first_filing_dates=series_registry,
        search_start_date=start_date,
        today=as_of,
    )
    frame = frame.sort_values(
        by=["date", "link", "ticker", "etf_name"],
        ascending=[False, True, True, True],
        kind="stable",
    )
    frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")
    frame["earliest_auto_effective_date"] = frame[
        "earliest_auto_effective_date"
    ].dt.strftime("%Y-%m-%d").fillna("")
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
