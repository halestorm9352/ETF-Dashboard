from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable
import unicodedata

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
BRIEF_FILENAME = "launch_brief.md"
STATE_FILENAME = "launch_brief_state.json"
TOP_COUNT_LIMIT = 5


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _normalized_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


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


def pipeline_identity(row: dict[str, Any]) -> str:
    cik = str(row.get("cik", "") or "").strip()
    series_id = str(row.get("series_id", "") or "").strip().upper()
    class_id = str(row.get("class_id", "") or "").strip().upper()
    if series_id or class_id:
        return f"{cik}:{series_id}:{class_id}"
    return f"{cik}:name:{_normalized_name(row.get('etf_name', ''))}"


def compute_delta(
    current_rows: Iterable[dict[str, Any]],
    previous_ids: Iterable[str],
) -> tuple[list[dict[str, Any]], set[str]]:
    rows = list(current_rows)
    previous = {str(identity) for identity in previous_ids}
    current_ids = {pipeline_identity(row) for row in rows}
    new_rows = [row for row in rows if pipeline_identity(row) not in previous]
    return new_rows, current_ids


def _top_counts(
    rows: Iterable[dict[str, Any]],
    field: str,
    fallback: str,
) -> list[tuple[str, int]]:
    counts = Counter(str(row.get(field, "") or fallback) for row in rows)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[
        :TOP_COUNT_LIMIT
    ]


def _display_date(value: Any) -> str:
    if value is None or value == "":
        return "Not detected"
    try:
        if pd.isna(value):
            return "Not detected"
    except (TypeError, ValueError):
        pass
    try:
        return _date_value(value).isoformat()
    except (TypeError, ValueError):
        return "Not detected"


def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    effective_date = _display_date(row.get("earliest_auto_effective_date"))
    if effective_date == "Not detected":
        effective_date = "9999-12-31"
    return (
        effective_date,
        str(row.get("filer", "") or ""),
        str(row.get("etf_name", "") or ""),
        pipeline_identity(row),
    )


def render_brief(
    current_rows: Iterable[dict[str, Any]],
    new_rows: Iterable[dict[str, Any]],
    today,
    is_first_run: bool,
    previous_as_of: Any = None,
) -> str:
    as_of = _date_value(today)
    current = list(current_rows)
    new = sorted(list(new_rows), key=_row_sort_key)
    upcoming_count = sum(
        row.get("launch_readiness") == UPCOMING_LAUNCH for row in current
    )
    initial_count = sum(
        row.get("launch_readiness") == INITIAL_REVIEW for row in current
    )

    lines = [
        f"# Launch Pipeline Brief -- as of {as_of.isoformat()}",
        "",
        (
            f"**Forward pipeline:** {len(current)} funds "
            f"({upcoming_count} upcoming, {initial_count} initial review)."
        ),
    ]
    if is_first_run:
        lines.append(
            "**Baseline brief:** no prior state was found; all current pipeline "
            "entries establish the baseline."
        )
    else:
        lines.append(f"**New since the last brief:** {len(new)}.")

    lines.extend(["", "## Top Filers", ""])
    filer_counts = _top_counts(current, "filer", "Unknown filer")
    lines.extend(
        [f"- {name}: {count}" for name, count in filer_counts]
        or ["- None"]
    )

    lines.extend(["", "## Top Themes", ""])
    theme_counts = _top_counts(current, "theme", "Other")
    lines.extend(
        [f"- {name}: {count}" for name, count in theme_counts]
        or ["- None"]
    )

    lines.extend(["", "## New This Period", ""])
    if new:
        for row in new:
            ticker = str(row.get("ticker", "") or "Not Listed").strip()
            if not ticker or ticker == "Not Listed":
                ticker = "Not Listed"
            if _truthy(row.get("needs_ticker")):
                ticker += " (ticker needed)"
            days = row.get("days_to_readiness", "")
            days_text = "N/A" if days in (None, "") else str(days)
            lines.append(
                f"- **{str(row.get('etf_name', '') or 'Unnamed fund')}** "
                f"({ticker}) - Filer: {str(row.get('filer', '') or 'Unknown filer')}; "
                f"Theme: {str(row.get('theme', '') or 'Other')}; "
                f"Vehicle: {str(row.get('vehicle', '') or 'Unknown')}; "
                f"Form: {str(row.get('form', '') or 'Unknown')}; "
                f"Effective date: {_display_date(row.get('earliest_auto_effective_date'))}; "
                f"Days to effective: {days_text}."
            )
    elif is_first_run:
        lines.append("No forward pipeline entries are present in this baseline brief.")
    else:
        since = _display_date(previous_as_of or as_of)
        lines.append(f"No new pipeline entries since {since}.")

    return "\n".join(lines) + "\n"


def _load_state(state_path: Path) -> tuple[set[str], str, bool]:
    if not state_path.is_file():
        return set(), "", True
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(), "", True
    previous_ids = {
        str(identity) for identity in state.get("pipeline_ids", [])
    }
    return previous_ids, str(state.get("generated_at", "")), False


def generate_brief(store_path, today) -> str:
    store = Path(store_path)
    as_of = _date_value(today)
    output_dir = store.resolve().parent
    brief_path = output_dir / BRIEF_FILENAME
    state_path = output_dir / STATE_FILENAME

    current_rows = build_forward_pipeline(store, as_of)
    previous_ids, previous_as_of, is_first_run = _load_state(state_path)
    new_rows, current_ids = compute_delta(current_rows, previous_ids)
    markdown = render_brief(
        current_rows,
        new_rows,
        as_of,
        is_first_run,
        previous_as_of=previous_as_of,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(markdown, encoding="utf-8", newline="\n")
    state = {
        "generated_at": f"{as_of.isoformat()}T00:00:00Z",
        "pipeline_ids": sorted(current_ids),
    }
    state_path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic markdown ETF launch-pipeline brief."
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
    markdown = generate_brief(args.store, args.today or date.today())
    print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
