from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any, Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import CIKS
from readiness import (
    DEFAULT_VISIBLE_STATUSES,
    INITIAL_REVIEW,
    UPCOMING_LAUNCH,
    add_launch_readiness_columns,
)
from sec_filings import (
    derive_latest_fund_rows,
    finalize_event_rows,
    normalize_event_ticker,
)
from store import get_series_registry, load_events, open_store
from theme_classifier import classify_primary_theme


DEFAULT_STORE_PATH = PROJECT_ROOT / "data" / "etf_dash.sqlite"
BRIEF_FILENAME = "launch_brief.json"
TOP_COUNT_LIMIT = 8


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def build_forward_pipeline(store_path, today) -> list[dict[str, Any]]:
    as_of = _date_value(today)
    start_date = date(as_of.year, 1, 1)
    handle = open_store(store_path)
    try:
        events = load_events(handle, start_date, as_of, ciks=CIKS)
        series_registry = get_series_registry(handle)
    finally:
        handle.close()

    finalized_events = finalize_event_rows(events, start_date, as_of)
    snapshot_rows = derive_latest_fund_rows(finalized_events)
    if not snapshot_rows:
        return []

    frame = pd.DataFrame(snapshot_rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).copy()
    if frame.empty:
        return []

    frame["ticker"] = frame.apply(
        lambda row: normalize_event_ticker(row.to_dict()),
        axis=1,
    )
    frame["theme"] = frame["etf_name"].apply(classify_primary_theme)
    frame = add_launch_readiness_columns(
        frame,
        series_first_filing_dates=series_registry,
        search_start_date=start_date,
        today=as_of,
    )
    frame = frame[
        frame["launch_readiness"].isin(DEFAULT_VISIBLE_STATUSES)
    ].copy()
    if frame.empty:
        return []

    frame = frame.sort_values(
        by=["earliest_auto_effective_date", "filer", "etf_name", "event_id"],
        ascending=[True, True, True, True],
        na_position="last",
        kind="stable",
    )
    return frame.to_dict(orient="records")


def _top_counts(
    rows: Iterable[dict[str, Any]],
    field: str,
    fallback: str,
) -> list[dict[str, Any]]:
    counts = Counter(str(row.get(field, "") or fallback) for row in rows)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [
        {"name": name, "count": count}
        for name, count in ranked[:TOP_COUNT_LIMIT]
    ]


def build_brief_data(
    current_rows: Iterable[dict[str, Any]],
    today,
) -> dict[str, Any]:
    current = list(current_rows)
    return {
        "as_of": _date_value(today).isoformat(),
        "total": len(current),
        "upcoming": sum(
            row.get("launch_readiness") == UPCOMING_LAUNCH for row in current
        ),
        "initial_review": sum(
            row.get("launch_readiness") == INITIAL_REVIEW for row in current
        ),
        "top_filers": _top_counts(current, "filer", "Unknown filer"),
        "top_themes": _top_counts(current, "theme", "Other"),
    }


def generate_brief(store_path, today) -> dict[str, Any]:
    store = Path(store_path)
    as_of = _date_value(today)
    output_dir = store.resolve().parent
    brief_path = output_dir / BRIEF_FILENAME
    brief = build_brief_data(build_forward_pipeline(store, as_of), as_of)

    output_dir.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        json.dumps(brief, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return brief


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic ETF launch-pipeline summary."
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=DEFAULT_STORE_PATH,
        help="SQLite filing store (default: data/etf_dash.sqlite).",
    )
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="As-of date in YYYY-MM-DD format (default: today).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    brief = generate_brief(args.store, args.today or date.today())
    print(json.dumps(brief, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
