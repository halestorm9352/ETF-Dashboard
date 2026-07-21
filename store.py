from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Any, Iterable


SCHEMA_VERSION = 1
EVENT_FIELDS = (
    "event_id",
    "accession_number",
    "cik",
    "form",
    "date",
    "accepted_at",
    "etf_name",
    "class_name",
    "series_name",
    "series_id",
    "class_id",
    "ticker",
    "ticker_at_filing",
    "ticker_source",
    "vehicle",
    "identity_scope",
    "filer",
    "link",
    "effectiveness_basis",
    "effectiveness_days",
    "designated_effective_date",
    "effectiveness_label",
)
TEXT_EVENT_FIELDS = tuple(
    field for field in EVENT_FIELDS if field != "effectiveness_days"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return str(value)


def open_store(path) -> sqlite3.Connection:
    store_path = Path(path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    handle = sqlite3.connect(store_path)
    handle.row_factory = sqlite3.Row
    try:
        handle.executescript(
            """
            CREATE TABLE IF NOT EXISTS store_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS filing_events (
                event_id TEXT PRIMARY KEY,
                accession_number TEXT,
                cik TEXT,
                form TEXT,
                date TEXT,
                accepted_at TEXT,
                etf_name TEXT,
                class_name TEXT,
                series_name TEXT,
                series_id TEXT,
                class_id TEXT,
                ticker TEXT,
                ticker_at_filing TEXT,
                ticker_source TEXT,
                vehicle TEXT,
                identity_scope TEXT,
                filer TEXT,
                link TEXT,
                effectiveness_basis TEXT,
                effectiveness_days INTEGER,
                designated_effective_date TEXT,
                effectiveness_label TEXT,
                ingested_at TEXT NOT NULL,
                parser_version INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_filing_events_cik_date
                ON filing_events(cik, date);
            CREATE INDEX IF NOT EXISTS idx_filing_events_series_id
                ON filing_events(series_id);
            CREATE INDEX IF NOT EXISTS idx_filing_events_accession
                ON filing_events(accession_number);

            CREATE TABLE IF NOT EXISTS processed_filings (
                accession_number TEXT PRIMARY KEY,
                cik TEXT,
                form TEXT,
                filing_date TEXT,
                parser_version INTEGER NOT NULL,
                event_count INTEGER NOT NULL,
                ingested_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS series_registry (
                series_id TEXT PRIMARY KEY,
                cik TEXT,
                first_filing_date TEXT NOT NULL,
                lookup_source TEXT NOT NULL,
                resolved_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ingest_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                start_bound TEXT NOT NULL,
                end_bound TEXT NOT NULL,
                ciks_attempted INTEGER NOT NULL,
                ciks_failed INTEGER NOT NULL,
                filings_processed INTEGER NOT NULL,
                events_added INTEGER NOT NULL,
                error_summary TEXT
            );
            """
        )
        metadata = {
            row["key"]: row["value"]
            for row in handle.execute("SELECT key, value FROM store_meta")
        }
        stored_version = metadata.get("schema_version")
        if stored_version is not None and stored_version != str(SCHEMA_VERSION):
            raise RuntimeError(
                "ETF Dashboard store schema version mismatch: "
                f"expected {SCHEMA_VERSION}, found {stored_version}."
            )
        if stored_version is None:
            handle.executemany(
                "INSERT INTO store_meta(key, value) VALUES (?, ?)",
                (
                    ("schema_version", str(SCHEMA_VERSION)),
                    ("backfill_floor", (date.today() - timedelta(days=365)).isoformat()),
                    ("created_at", _utc_now()),
                ),
            )
        handle.commit()
        return handle
    except Exception:
        handle.close()
        raise


def upsert_events(
    handle: sqlite3.Connection,
    events: Iterable[dict[str, Any]],
    parser_version: int,
) -> dict[str, int]:
    added = 0
    updated = 0
    ingested_at = _utc_now()
    update_fields = EVENT_FIELDS[1:] + ("ingested_at", "parser_version")
    placeholders = ", ".join("?" for _ in (*EVENT_FIELDS, "ingested_at", "parser_version"))
    update_clause = ", ".join(f"{field}=excluded.{field}" for field in update_fields)
    sql = (
        f"INSERT INTO filing_events ({', '.join(EVENT_FIELDS)}, ingested_at, parser_version) "
        f"VALUES ({placeholders}) ON CONFLICT(event_id) DO UPDATE SET {update_clause}"
    )

    with handle:
        for event in events:
            event_id = str(event.get("event_id", "") or "").strip()
            if not event_id:
                raise ValueError("Stored filing events require a non-empty event_id.")
            exists = handle.execute(
                "SELECT 1 FROM filing_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            values: list[Any] = []
            for field in EVENT_FIELDS:
                value = event.get(field, "")
                if field == "effectiveness_days":
                    value = value if value in (None, "") else int(value)
                else:
                    value = "" if value is None else str(value)
                values.append(value)
            handle.execute(sql, (*values, ingested_at, int(parser_version)))
            if exists:
                updated += 1
            else:
                added += 1
    return {"events_added": added, "events_updated": updated}


def record_processed_filing(
    handle: sqlite3.Connection,
    accession,
    cik,
    form,
    filing_date,
    parser_version,
    event_count,
) -> None:
    with handle:
        handle.execute(
            """
            INSERT INTO processed_filings (
                accession_number, cik, form, filing_date, parser_version,
                event_count, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(accession_number) DO UPDATE SET
                cik=excluded.cik,
                form=excluded.form,
                filing_date=excluded.filing_date,
                parser_version=excluded.parser_version,
                event_count=excluded.event_count,
                ingested_at=excluded.ingested_at
            """,
            (
                str(accession),
                str(cik),
                str(form),
                _date_text(filing_date),
                int(parser_version),
                int(event_count),
                _utc_now(),
            ),
        )


def is_filing_processed(handle: sqlite3.Connection, accession) -> bool:
    return (
        handle.execute(
            "SELECT 1 FROM processed_filings WHERE accession_number = ?",
            (str(accession),),
        ).fetchone()
        is not None
    )


def processed_filing_parser_version(
    handle: sqlite3.Connection,
    accession,
) -> int | None:
    row = handle.execute(
        "SELECT parser_version FROM processed_filings WHERE accession_number = ?",
        (str(accession),),
    ).fetchone()
    return int(row["parser_version"]) if row is not None else None


def load_events(handle, start_date, end_date, ciks=None) -> list[dict[str, Any]]:
    clauses = ["date >= ?", "date <= ?"]
    parameters: list[Any] = [_date_text(start_date), _date_text(end_date)]
    if ciks is not None:
        selected_ciks = [str(cik) for cik in ciks]
        if not selected_ciks:
            return []
        clauses.append(f"cik IN ({', '.join('?' for _ in selected_ciks)})")
        parameters.extend(selected_ciks)
    rows = handle.execute(
        f"SELECT {', '.join(EVENT_FIELDS)} FROM filing_events "
        f"WHERE {' AND '.join(clauses)} ORDER BY date DESC, accepted_at DESC, event_id",
        parameters,
    ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        event = {field: row[field] for field in EVENT_FIELDS}
        for field in TEXT_EVENT_FIELDS:
            event[field] = event[field] or ""
        events.append(event)
    return events


def get_series_registry(handle) -> dict[str, str]:
    return {
        row["series_id"]: row["first_filing_date"]
        for row in handle.execute(
            "SELECT series_id, first_filing_date FROM series_registry ORDER BY series_id"
        )
    }


def upsert_series_registration(
    handle,
    series_id,
    cik,
    first_filing_date,
    lookup_source,
) -> None:
    with handle:
        handle.execute(
            """
            INSERT INTO series_registry (
                series_id, cik, first_filing_date, lookup_source, resolved_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(series_id) DO UPDATE SET
                cik=excluded.cik,
                first_filing_date=excluded.first_filing_date,
                lookup_source=excluded.lookup_source,
                resolved_at=excluded.resolved_at
            """,
            (
                str(series_id).strip().upper(),
                str(cik),
                _date_text(first_filing_date),
                str(lookup_source),
                _utc_now(),
            ),
        )


def record_ingest_run(handle, run: dict[str, Any]) -> int:
    fields = (
        "mode",
        "started_at",
        "completed_at",
        "start_bound",
        "end_bound",
        "ciks_attempted",
        "ciks_failed",
        "filings_processed",
        "events_added",
        "error_summary",
    )
    values = [run.get(field, "") for field in fields]
    values[3] = _date_text(values[3])
    values[4] = _date_text(values[4])
    with handle:
        cursor = handle.execute(
            f"INSERT INTO ingest_runs ({', '.join(fields)}) "
            f"VALUES ({', '.join('?' for _ in fields)})",
            values,
        )
    return int(cursor.lastrowid)


def get_last_successful_ingest(handle) -> dict[str, Any] | None:
    row = handle.execute(
        """
        SELECT * FROM ingest_runs
        WHERE completed_at IS NOT NULL
          AND completed_at != ''
          AND ciks_attempted > ciks_failed
        ORDER BY run_id DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row is not None else None
