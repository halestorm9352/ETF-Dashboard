from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree

import requests

from config import (
    CIKS,
    CIK_LOOKUP,
    DAYS_BACK,
    FORMS,
    INDEX_PAGE_MAX_CHARS,
    MAX_SUPPORTING_DOCUMENTS,
    PRIMARY_IDENTITY_MAX_CHARS,
    PRIMARY_DOCUMENT_MAX_CHARS,
    SEC_MAX_WORKERS,
)

SEC_FUND_TICKER_URL = "https://www.sec.gov/files/company_tickers_mf.json"
SEC_FUND_TICKER_MAX_CHARS = 20_000_000
from http_utils import get_response as get_http_response, get_response_text
from sec_parsers import (
    detect_exchange_listed,
    extract_etf_name,
    extract_filer_name,
    extract_named_ticker_pairs,
    extract_rule_485_effectiveness,
    extract_series_entries,
    extract_supporting_document_urls,
    extract_ticker,
    normalize_etf_name,
    sanitize_ticker,
)
from vehicle_classifier import (
    ETF_VEHICLE,
    MUTUAL_FUND_SHARE_CLASS,
    UNKNOWN_VEHICLE,
    classify_vehicle,
    is_mutual_fund_ticker,
    is_share_class_name,
    uses_parent_series_identity,
)


MODULE_CONTRACT_VERSION = 12
SERIES_FEED_PAGE_SIZE = 100
SERIES_FEED_MAX_PAGES = 100
ATOM_NAMESPACE = "{http://www.w3.org/2005/Atom}"
EXCHANGE_NAME_PREFIX = re.compile(
    r"^(?:BZX|NYSE|NASDAQ|CBOE|ARCA)\b",
    re.IGNORECASE,
)


class FilingEventResults(list[dict[str, str]]):
    def __init__(
        self,
        events: list[dict[str, str]] | None = None,
        statuses: list[dict[str, Any]] | None = None,
        mapping_status: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(events or [])
        self.statuses = statuses or []
        self.mapping_status = mapping_status or {
            "available": True,
            "error_summary": "",
        }


class SecFundTickerMapping(dict[tuple[str, str, str], str]):
    def __init__(
        self,
        values: dict[tuple[str, str, str], str] | None = None,
        *,
        available: bool,
        error_summary: str = "",
    ) -> None:
        super().__init__(values or {})
        self.available = available
        self.error_summary = error_summary


def extract_text(url: str, max_chars: int = INDEX_PAGE_MAX_CHARS) -> str:
    return get_response_text(url, max_chars)


def fetch_series_registration_date(series_id: str) -> dict[str, Any]:
    normalized_series_id = str(series_id or "").strip().upper()
    status: dict[str, Any] = {
        "series_id": normalized_series_id,
        "success": False,
        "first_filing_date": "",
        "error_summary": "",
    }
    if not re.fullmatch(r"S\d{9}", normalized_series_id):
        status["error_summary"] = "Invalid SEC series ID"
        return status

    query = {
        "action": "getcompany",
        "CIK": normalized_series_id,
        "output": "atom",
        "count": SERIES_FEED_PAGE_SIZE,
        "start": 0,
    }
    next_url = f"https://www.sec.gov/cgi-bin/browse-edgar?{urlencode(query)}"
    filing_dates: list[datetime] = []
    seen_urls: set[str] = set()

    try:
        for _ in range(SERIES_FEED_MAX_PAGES):
            if not next_url:
                break
            if next_url in seen_urls:
                status["error_summary"] = "SEC series filing history repeated a page"
                return status
            seen_urls.add(next_url)
            response = get_http_response(next_url)
            root = ElementTree.fromstring(response.text)
            entries = root.findall(f"{ATOM_NAMESPACE}entry")
            for entry in entries:
                filing_date = entry.findtext(
                    f".//{ATOM_NAMESPACE}filing-date",
                    default="",
                ).strip()
                if filing_date:
                    filing_dates.append(datetime.strptime(filing_date, "%Y-%m-%d"))

            next_link = root.find(f"{ATOM_NAMESPACE}link[@rel='next']")
            next_url = (
                str(next_link.get("href", "") or "").strip()
                if next_link is not None
                else ""
            )
        else:
            status["error_summary"] = "SEC series filing history exceeded pagination limit"
            return status
    except Exception as exc:
        status["error_summary"] = f"{type(exc).__name__}: {exc}"
        return status

    if not filing_dates:
        status["error_summary"] = "SEC series filing history returned no filing dates"
        return status

    status["success"] = True
    status["first_filing_date"] = min(filing_dates).date().isoformat()
    return status


def fetch_supporting_document_texts(
    index_text: str,
    max_documents: int = MAX_SUPPORTING_DOCUMENTS,
    excluded_urls: set[str] | None = None,
) -> list[str]:
    documents: list[str] = []
    excluded = excluded_urls or set()
    candidate_urls = [
        url
        for url in extract_supporting_document_urls(index_text)
        if url not in excluded
        and url.lower().split("?", 1)[0].endswith((".htm", ".html", ".xml", ".txt"))
    ]
    for url in candidate_urls[:max_documents]:
        max_chars = 300000
        if url.lower().endswith("_htm.xml"):
            max_chars = 120000

        text = extract_text(url, max_chars=max_chars)
        if text:
            documents.append(text)

    return documents


def fetch_recent_filings_for_cik(cik: str) -> dict[str, Any]:
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        response = get_http_response(url, retries=3, timeout=20)
        data = response.json()
        return {
            "filer_name": data.get("name", CIK_LOOKUP.get(cik, cik)),
            "recent": data.get("filings", {}).get("recent", {}),
        }
    except (requests.RequestException, ValueError) as exc:
        return {
            "filer_name": CIK_LOOKUP.get(cik, cik),
            "recent": {},
            "_error": f"{type(exc).__name__}: {exc}",
        }


def _normalized_cik(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(10) if digits else ""


def _official_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    return ticker if re.fullmatch(r"[A-Z0-9.\-]{1,10}", ticker) else ""


def fetch_sec_fund_ticker_mapping() -> SecFundTickerMapping:
    try:
        text = get_response_text(SEC_FUND_TICKER_URL, SEC_FUND_TICKER_MAX_CHARS)
    except Exception as exc:
        return SecFundTickerMapping(
            available=False,
            error_summary=f"{type(exc).__name__}: {exc}",
        )
    if not text:
        return SecFundTickerMapping(
            available=False,
            error_summary="SEC fund-ticker mapping returned no data",
        )

    try:
        payload = json.loads(text)
        fields = list(payload.get("fields", []))
        positions = {field: index for index, field in enumerate(fields)}
        required = {"cik", "seriesId", "classId", "symbol"}
        if not required.issubset(positions):
            return SecFundTickerMapping(
                available=False,
                error_summary="SEC fund-ticker mapping fields are incomplete",
            )

        mapping: dict[tuple[str, str, str], str] = {}
        for values in payload.get("data", []):
            cik = _normalized_cik(values[positions["cik"]])
            series_id = str(values[positions["seriesId"]] or "").strip().upper()
            class_id = str(values[positions["classId"]] or "").strip().upper()
            ticker = _official_ticker(values[positions["symbol"]])
            if cik and series_id and class_id and ticker:
                mapping[(cik, series_id, class_id)] = ticker
        return SecFundTickerMapping(mapping, available=True)
    except (IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return SecFundTickerMapping(
            available=False,
            error_summary=f"{type(exc).__name__}: {exc}",
        )


def normalize_event_ticker(row: dict[str, Any]) -> str:
    if row.get("ticker_source") == "sec_fund_ticker_map":
        ticker = _official_ticker(row.get("ticker", ""))
        if ticker:
            return ticker
    if (
        row.get("vehicle") == MUTUAL_FUND_SHARE_CLASS
        and is_mutual_fund_ticker(row.get("ticker", ""))
    ):
        return str(row.get("ticker", "")).strip().upper()
    return sanitize_ticker(row.get("ticker", ""))


def _needs_primary_document(
    series_entries: list[dict[str, str]],
    filing_filer_name: str,
) -> bool:
    if not series_entries or not filing_filer_name:
        return True
    return any((not entry.get("ticker")) or (not entry.get("etf_name")) for entry in series_entries)


def _needs_supporting_documents(
    series_entries: list[dict[str, str]],
    primary_ticker: str,
    primary_etf_name: str,
    filing_filer_name: str,
) -> bool:
    if not series_entries:
        return not primary_ticker or primary_etf_name == "N/A" or not filing_filer_name
    if not filing_filer_name:
        return True
    return any(not entry.get("ticker") for entry in series_entries)


def _merge_series_entries_with_pairs(
    series_entries: list[dict[str, str]],
    named_ticker_pairs: list[dict[str, str]],
) -> list[dict[str, str]]:
    if not series_entries or not named_ticker_pairs:
        return series_entries

    merged_entries = [dict(entry) for entry in series_entries]
    pair_lookup: dict[str, str] = {}
    for pair in named_ticker_pairs:
        normalized_name = normalize_etf_name(pair.get("etf_name", ""))
        ticker = sanitize_ticker(pair.get("ticker", ""))
        if normalized_name and ticker != "Not Listed":
            pair_lookup[normalized_name] = ticker

    proposed_tickers: dict[int, str] = {}
    for index, entry in enumerate(merged_entries):
        if entry.get("ticker"):
            continue
        normalized_entry_name = normalize_etf_name(entry.get("etf_name", ""))
        if normalized_entry_name in pair_lookup:
            proposed_tickers[index] = pair_lookup[normalized_entry_name]
            continue
        for pair_name, pair_ticker in pair_lookup.items():
            if normalized_entry_name and (
                normalized_entry_name in pair_name or pair_name in normalized_entry_name
            ):
                proposed_tickers[index] = pair_ticker
                break

    proposal_counts: dict[str, int] = {}
    for ticker in proposed_tickers.values():
        proposal_counts[ticker] = proposal_counts.get(ticker, 0) + 1
    table_tickers: set[str] = set()
    for entry in merged_entries:
        table_ticker = sanitize_ticker(entry.get("ticker", ""))
        if table_ticker != "Not Listed":
            table_tickers.add(table_ticker)

    for index, ticker in proposed_tickers.items():
        if proposal_counts[ticker] == 1 and ticker not in table_tickers:
            merged_entries[index]["ticker"] = ticker

    return merged_entries


def _mapping_validated_prospectus_entries(
    cik: str,
    named_ticker_pairs: list[dict[str, str]],
    mapping: dict[tuple[str, str, str], str],
    series_entries: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    normalized_cik = _normalized_cik(cik)
    identities_by_ticker: dict[str, set[tuple[str, str]]] = {}
    for (mapped_cik, series_id, class_id), symbol in mapping.items():
        if _normalized_cik(mapped_cik) != normalized_cik:
            continue
        ticker = _official_ticker(symbol)
        if ticker:
            identities_by_ticker.setdefault(ticker, set()).add(
                (str(series_id).strip().upper(), str(class_id).strip().upper())
            )

    existing_identities = {
        (
            str(entry.get("series_id", "") or "").strip().upper(),
            str(entry.get("class_id", "") or "").strip().upper(),
        )
        for entry in (series_entries or [])
        if entry.get("series_id") and entry.get("class_id")
    }
    pairs_by_ticker: dict[str, list[dict[str, str]]] = {}
    for pair in named_ticker_pairs:
        ticker = _official_ticker(pair.get("ticker", ""))
        name = str(pair.get("etf_name", "") or "").strip()
        if ticker in identities_by_ticker and name:
            pairs_by_ticker.setdefault(ticker, []).append(pair)

    retained: list[dict[str, str]] = []
    for ticker, pairs in pairs_by_ticker.items():
        identities = identities_by_ticker[ticker]
        if len(identities) == 1:
            series_id, class_id = next(iter(identities))
            if (series_id, class_id) in existing_identities:
                continue
            clean_pair = max(
                pairs,
                key=lambda pair: int(
                    not EXCHANGE_NAME_PREFIX.match(
                        str(pair.get("etf_name", "") or "").strip()
                    )
                ),
            )
            clean_name = str(clean_pair.get("etf_name", "") or "").strip()
            retained.append(
                {
                    "ticker": ticker,
                    "ticker_at_filing": ticker,
                    "ticker_source": "filing",
                    "etf_name": clean_name,
                    "class_name": clean_name,
                    "series_id": series_id,
                    "series_name": clean_name,
                    "class_id": class_id,
                    "vehicle": ETF_VEHICLE,
                    "identity_scope": "class",
                }
            )
            continue

        seen_names: set[str] = set()
        for pair in pairs:
            name = str(pair.get("etf_name", "") or "").strip()
            normalized_name = normalize_etf_name(name)
            if not normalized_name or normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)
            retained.append(
                {
                    "ticker": ticker,
                    "ticker_at_filing": ticker,
                    "ticker_source": "filing",
                    "etf_name": name,
                    "class_name": name,
                    "series_id": "",
                    "series_name": "",
                    "class_id": "",
                    "vehicle": ETF_VEHICLE,
                    "identity_scope": "name",
                }
            )
    return retained


def _display_filer_name(cik: str, filer_name: str) -> str:
    configured_name = CIK_LOOKUP.get(cik, "")
    normalized_name = str(configured_name or filer_name or "").upper()
    if cik in {"0001742912", "0001924868"} or "TIDAL TRUST" in normalized_name:
        return "TIDAL"
    return normalized_name


def _row_timestamp(row: dict[str, str]) -> datetime:
    accepted_at = str(row.get("accepted_at", "")).strip()
    if accepted_at:
        try:
            parsed = datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            pass

    try:
        return datetime.strptime(str(row.get("date", "")), "%Y-%m-%d")
    except ValueError:
        return datetime.min


def _row_filing_date(row: dict[str, str]) -> datetime:
    try:
        return datetime.strptime(str(row.get("date", "")), "%Y-%m-%d")
    except ValueError:
        return datetime.min


def _effective_filing_date(row: dict[str, Any]) -> datetime:
    designated_date = str(row.get("designated_effective_date", "") or "").strip()
    if designated_date:
        for date_format in ("%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(designated_date, date_format)
            except ValueError:
                continue
        return datetime.max

    effectiveness_days = row.get("effectiveness_days")
    try:
        days = int(effectiveness_days)
    except (TypeError, ValueError):
        return datetime.max
    filing_date = _row_filing_date(row)
    return filing_date + timedelta(days=days) if filing_date != datetime.min else datetime.max


def _filter_rows_to_bounds(
    rows: list[dict[str, str]],
    start_bound: datetime,
    end_bound: datetime,
) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if start_bound <= _row_filing_date(row) <= end_bound
    ]


def _has_sec_identity(row: dict[str, Any]) -> bool:
    return bool(str(row.get("series_id", "")).strip() or str(row.get("class_id", "")).strip())


def _sec_identity(row: dict[str, Any]) -> tuple[str, str, str, str] | None:
    cik = _normalized_cik(row.get("cik", ""))
    series_id = str(row.get("series_id", "") or "").strip().upper()
    class_id = str(row.get("class_id", "") or "").strip().upper()
    if cik and series_id and row.get("identity_scope") == "series":
        return ("sec_series", cik, series_id, "")
    if cik and series_id and class_id:
        return ("sec_class", cik, series_id, class_id)
    if cik and series_id:
        return ("sec_series", cik, series_id, "")
    return None


def _identity_aliases(
    rows: list[dict[str, str]],
) -> dict[tuple[str, str], tuple[str, str, str, str]]:
    identities_by_name: dict[
        tuple[str, str], set[tuple[str, str, str, str]]
    ] = {}
    for row in rows:
        identity = _sec_identity(row)
        normalized_name = normalize_etf_name(row.get("etf_name", ""))
        if not identity or not normalized_name:
            continue
        name_key = (_normalized_cik(row.get("cik", "")), normalized_name)
        identities_by_name.setdefault(name_key, set()).add(identity)

    return {
        name_key: next(iter(identities))
        for name_key, identities in identities_by_name.items()
        if len(identities) == 1
    }


def _fund_identity(
    row: dict[str, Any],
    aliases: dict[tuple[str, str], tuple[str, str, str, str]] | None = None,
) -> tuple[str, str, str, str]:
    identity = _sec_identity(row)
    if identity:
        return identity

    cik = _normalized_cik(row.get("cik", ""))
    normalized_name = normalize_etf_name(row.get("etf_name", ""))
    if aliases and (cik, normalized_name) in aliases:
        return aliases[(cik, normalized_name)]
    return ("name", cik, normalized_name, "")


def _enrich_tickers_from_sec_mapping(
    rows: list[dict[str, str]],
    mapping: dict[tuple[str, str, str], str],
) -> list[dict[str, str]]:
    for row in rows:
        if sanitize_ticker(row.get("ticker", "")) != "Not Listed":
            continue

        key = (
            _normalized_cik(row.get("cik", "")),
            str(row.get("series_id", "") or "").strip().upper(),
            str(row.get("class_id", "") or "").strip().upper(),
        )
        ticker = mapping.get(key, "")
        if ticker:
            row["ticker"] = ticker
            row["ticker_source"] = "sec_fund_ticker_map"
    return rows


def _enrich_series_entries_from_sec_mapping(
    cik: str,
    entries: list[dict[str, str]],
    mapping: dict[tuple[str, str, str], str],
) -> list[dict[str, str]]:
    for entry in entries:
        raw_ticker = str(entry.get("ticker", "") or "").strip().upper()
        filing_ticker = (
            raw_ticker if is_mutual_fund_ticker(raw_ticker) else sanitize_ticker(raw_ticker)
        )
        entry["ticker_at_filing"] = filing_ticker
        entry["ticker_source"] = (
            "filing" if filing_ticker != "Not Listed" else "not_listed"
        )
        if filing_ticker == "Not Listed":
            key = (
                _normalized_cik(cik),
                str(entry.get("series_id", "") or "").strip().upper(),
                str(entry.get("class_id", "") or "").strip().upper(),
            )
            ticker = mapping.get(key, "")
            if ticker:
                entry["ticker"] = ticker
                entry["ticker_source"] = "sec_fund_ticker_map"

        entry["vehicle"] = classify_vehicle(entry)
        entry["identity_scope"] = (
            "series" if uses_parent_series_identity(entry) else "class"
        )
    return entries


def _enrich_missing_tickers_from_later_filings(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    latest_ticker_by_fund: dict[tuple[str, str], str] = {}
    enriched_rows = sorted(rows, key=_row_timestamp, reverse=True)

    for row in enriched_rows:
        if _has_sec_identity(row):
            continue
        normalized_name = normalize_etf_name(row.get("etf_name", ""))
        if not normalized_name:
            continue

        key = (row.get("cik", ""), normalized_name)
        ticker = sanitize_ticker(row.get("ticker", ""))
        if ticker != "Not Listed":
            latest_ticker_by_fund.setdefault(key, ticker)
        elif key in latest_ticker_by_fund:
            row["ticker"] = latest_ticker_by_fund[key]
            row["ticker_source"] = "later_filing_fallback"

    return _normalize_vehicle_identity_metadata(rows)


def _normalize_vehicle_identity_metadata(
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    series_scoped_classes: set[tuple[str, str, str]] = set()
    for row in rows:
        stored_vehicle = row.get("vehicle")
        computed_vehicle = classify_vehicle(row)
        row["vehicle"] = (
            stored_vehicle
            if computed_vehicle == UNKNOWN_VEHICLE
            and stored_vehicle in {ETF_VEHICLE, MUTUAL_FUND_SHARE_CLASS}
            else computed_vehicle
        )
        series_id = str(row.get("series_id", "") or "").strip().upper()
        class_id = str(row.get("class_id", "") or "").strip().upper()
        if series_id and class_id:
            row["identity_scope"] = (
                "series" if uses_parent_series_identity(row) else "class"
            )
            if row["identity_scope"] == "series":
                series_scoped_classes.add(
                    (_normalized_cik(row.get("cik", "")), series_id, class_id)
                )
        elif series_id:
            row["identity_scope"] = "series"
        else:
            row["identity_scope"] = "name"

    for row in rows:
        identity = (
            _normalized_cik(row.get("cik", "")),
            str(row.get("series_id", "") or "").strip().upper(),
            str(row.get("class_id", "") or "").strip().upper(),
        )
        if identity in series_scoped_classes:
            row["identity_scope"] = "series"
    return rows


def _dedupe_latest_fund_rows(
    rows: list[dict[str, str]],
    aliases: dict[tuple[str, str], tuple[str, str, str, str]] | None = None,
) -> list[dict[str, str]]:
    deduped_rows: list[dict[str, str]] = []
    seen_funds: set[tuple[str, str, str, str]] = set()

    vehicle_priority = {
        ETF_VEHICLE: 3,
        MUTUAL_FUND_SHARE_CLASS: 2,
        UNKNOWN_VEHICLE: 1,
    }

    def snapshot_sort_key(row: dict[str, str]) -> tuple[datetime, int, int, int, int]:
        class_name = normalize_etf_name(row.get("class_name", ""))
        series_name = normalize_etf_name(row.get("series_name", ""))
        clean_name = int(
            not EXCHANGE_NAME_PREFIX.match(
                str(row.get("etf_name", "") or "").strip()
            )
        )
        return (
            _row_timestamp(row),
            vehicle_priority.get(row.get("vehicle", ""), 0),
            int(normalize_event_ticker(row) != "Not Listed"),
            int(bool(class_name and class_name == series_name)),
            clean_name,
        )

    for row in sorted(rows, key=snapshot_sort_key, reverse=True):
        normalized_name = normalize_etf_name(row.get("etf_name", ""))
        key = _fund_identity(row, aliases)
        if not normalized_name:
            deduped_rows.append(row)
            continue
        if key in seen_funds:
            continue
        seen_funds.add(key)
        deduped_rows.append(row)

    return deduped_rows


def derive_latest_fund_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    copied_rows = _normalize_vehicle_identity_metadata([dict(row) for row in rows])
    aliases = _identity_aliases(copied_rows)
    history_by_fund: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for row in sorted(copied_rows, key=_row_timestamp):
        normalized_name = normalize_etf_name(row.get("etf_name", ""))
        if not normalized_name:
            continue
        key = _fund_identity(row, aliases)
        history_by_fund.setdefault(key, []).append(row)

    latest_rows = _dedupe_latest_fund_rows(copied_rows, aliases)
    for row in latest_rows:
        history = history_by_fund.get(_fund_identity(row, aliases), [row])
        unique_history: list[dict[str, str]] = []
        seen_accessions: set[str] = set()
        for event in history:
            accession = str(event.get("accession_number", "") or "").strip()
            if accession and accession in seen_accessions:
                continue
            if accession:
                seen_accessions.add(accession)
            unique_history.append(event)

        forms = [
            str(event.get("form", "") or "").upper()
            for event in unique_history
        ]
        forms = [form for form in forms if form]
        row["filing_event_count"] = len(unique_history)
        row["amendment_count"] = sum(
            form in {"485APOS", "485BPOS"} for form in forms
        )
        row["filing_form_history"] = " -> ".join(forms)
        row_date = _row_filing_date(row)
        row["prior_effective_485bpos"] = any(
            str(event.get("form", "") or "").upper() == "485BPOS"
            and _row_timestamp(event) < _row_timestamp(row)
            and _effective_filing_date(event) <= row_date
            for event in unique_history
        )

    return latest_rows


def _is_placeholder_share_class_name(name: str) -> bool:
    return is_share_class_name(name)


def _fetch_filing_rows_for_cik(
    cik: str,
    start_bound: datetime,
    end_bound: datetime,
    cik_data: dict[str, Any],
    primary_document_workers: int = 1,
    ticker_mapping: dict[tuple[str, str, str], str] | None = None,
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen_links: set[str] = set()
    filer_name = str(cik_data.get("filer_name", CIK_LOOKUP.get(cik, cik))).upper()
    recent = cik_data.get("recent", {})
    if not recent:
        return results

    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    accepted_times = recent.get("acceptanceDateTime", [])
    accession_numbers = recent.get("accessionNumber", [])
    primary_documents = recent.get("primaryDocument", [])

    primary_document_urls: set[str] = set()
    for index, form in enumerate(forms):
        if form not in {"485APOS", "485BPOS"}:
            continue
        if (
            index >= len(filing_dates)
            or index >= len(accession_numbers)
            or index >= len(primary_documents)
        ):
            continue
        date = datetime.strptime(filing_dates[index], "%Y-%m-%d")
        primary_document = primary_documents[index]
        if date < start_bound or date > end_bound or not primary_document:
            continue
        accession_clean = accession_numbers[index].replace("-", "")
        primary_document_urls.add(
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession_clean}/{primary_document}"
        )

    prefetched_primary_text: dict[str, str] = {}
    primary_worker_count = max(
        1,
        min(primary_document_workers, len(primary_document_urls)),
    )
    if primary_worker_count == 1:
        for url in primary_document_urls:
            prefetched_primary_text[url] = extract_text(
                url,
                max_chars=PRIMARY_DOCUMENT_MAX_CHARS,
            )
    elif primary_document_urls:
        with ThreadPoolExecutor(max_workers=primary_worker_count) as executor:
            future_map = {
                executor.submit(
                    extract_text,
                    url,
                    PRIMARY_DOCUMENT_MAX_CHARS,
                ): url
                for url in primary_document_urls
            }
            for future in as_completed(future_map):
                url = future_map[future]
                try:
                    prefetched_primary_text[url] = future.result()
                except requests.HTTPError:
                    raise
                except Exception:
                    prefetched_primary_text[url] = ""

    for index, form in enumerate(forms):
        if form not in FORMS:
            continue
        if index >= len(filing_dates) or index >= len(accession_numbers):
            continue

        date_str = filing_dates[index]
        accepted_at = accepted_times[index] if index < len(accepted_times) else ""
        date = datetime.strptime(date_str, "%Y-%m-%d")
        if date < start_bound or date > end_bound:
            continue

        accession_number = accession_numbers[index]
        accession_clean = accession_number.replace("-", "")
        filing_link = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession_clean}/{accession_number}-index.htm"
        )
        if filing_link in seen_links:
            continue
        seen_links.add(filing_link)

        primary_document = primary_documents[index] if index < len(primary_documents) else ""
        primary_document_url = ""
        if primary_document:
            primary_document_url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{accession_clean}/{primary_document}"
            )

        index_text = extract_text(filing_link, max_chars=INDEX_PAGE_MAX_CHARS)
        filing_filer_name = extract_filer_name(index_text) or filer_name
        series_entries = extract_series_entries(index_text)
        series_entries = _enrich_series_entries_from_sec_mapping(
            cik,
            series_entries,
            ticker_mapping or {},
        )
        primary_text = ""
        primary_ticker = ""
        primary_etf_name = "N/A"
        primary_named_pairs: list[dict[str, str]] = []
        primary_identity_text = ""
        exchange_listed = False

        needs_primary_text = _needs_primary_document(series_entries, filing_filer_name)
        needs_mapping_validated_pairs = bool(series_entries and ticker_mapping)
        needs_effectiveness_context = form in {"485APOS", "485BPOS"}
        if primary_document_url and (
            needs_primary_text
            or needs_mapping_validated_pairs
            or needs_effectiveness_context
        ):
            if primary_document_url in prefetched_primary_text:
                primary_text = prefetched_primary_text[primary_document_url]
            else:
                primary_text = extract_text(
                    primary_document_url,
                    max_chars=PRIMARY_DOCUMENT_MAX_CHARS,
                )
            if primary_text:
                primary_identity_text = primary_text[:PRIMARY_IDENTITY_MAX_CHARS]
                exchange_listed = detect_exchange_listed(primary_identity_text)
            if primary_text and (needs_primary_text or needs_mapping_validated_pairs):
                primary_named_pairs = extract_named_ticker_pairs(primary_identity_text)
                primary_ticker = extract_ticker(
                    primary_identity_text,
                    named_ticker_pairs=primary_named_pairs,
                )
                primary_etf_name = extract_etf_name(primary_identity_text)
                if not filing_filer_name:
                    filing_filer_name = extract_filer_name(primary_identity_text)

        supporting_named_pairs: list[dict[str, str]] = []
        if index_text and _needs_supporting_documents(
            series_entries,
            primary_ticker,
            primary_etf_name,
            filing_filer_name,
        ):
            excluded_urls = {primary_document_url} if primary_document_url else set()
            for supporting_text in fetch_supporting_document_texts(
                index_text,
                excluded_urls=excluded_urls,
            ):
                supporting_pairs = extract_named_ticker_pairs(supporting_text)
                if not primary_ticker:
                    primary_ticker = extract_ticker(
                        supporting_text,
                        named_ticker_pairs=supporting_pairs,
                    )
                if primary_etf_name == "N/A":
                    primary_etf_name = extract_etf_name(supporting_text)
                supporting_named_pairs.extend(supporting_pairs)
                if not filing_filer_name:
                    filing_filer_name = extract_filer_name(supporting_text)
                if primary_ticker and primary_etf_name != "N/A" and filing_filer_name:
                    break

        effectiveness = extract_rule_485_effectiveness(primary_text or index_text)
        all_named_pairs = primary_named_pairs + supporting_named_pairs
        mapped_prospectus_entries: list[dict[str, str]] = []
        if series_entries:
            series_entries = _merge_series_entries_with_pairs(series_entries, all_named_pairs)
            for entry in series_entries:
                if entry.get("ticker_source") == "sec_fund_ticker_map":
                    continue
                filing_ticker = sanitize_ticker(entry.get("ticker", ""))
                if filing_ticker != "Not Listed":
                    entry["ticker_at_filing"] = filing_ticker
                    entry["ticker_source"] = "filing"
            mapped_prospectus_entries = _mapping_validated_prospectus_entries(
                cik,
                all_named_pairs,
                ticker_mapping or {},
                series_entries,
            )

        resolved_filer_name = _display_filer_name(cik, filing_filer_name or filer_name)
        rows_to_append: list[dict[str, str]] = []

        if series_entries:
            for entry in series_entries:
                row_name = entry["etf_name"] or primary_etf_name
                row_ticker = entry["ticker"]
                if len(series_entries) == 1 and not row_ticker:
                    row_ticker = primary_ticker
                    primary_filing_ticker = sanitize_ticker(primary_ticker)
                    if primary_filing_ticker != "Not Listed":
                        entry["ticker_at_filing"] = primary_filing_ticker
                        entry["ticker_source"] = "filing"
                rows_to_append.append(
                    {
                        "ticker": (
                            _official_ticker(row_ticker)
                            if entry.get("ticker_source") == "sec_fund_ticker_map"
                            else sanitize_ticker(row_ticker)
                        ),
                        "ticker_at_filing": entry.get("ticker_at_filing", "Not Listed"),
                        "ticker_source": entry.get("ticker_source", "not_listed"),
                        "etf_name": row_name,
                        "class_name": entry.get("class_name", row_name),
                        "series_id": entry.get("series_id", ""),
                        "series_name": entry.get("series_name", ""),
                        "class_id": entry.get("class_id", ""),
                        "vehicle": entry.get("vehicle", UNKNOWN_VEHICLE),
                        "identity_scope": entry.get("identity_scope", "class"),
                        "filer": resolved_filer_name,
                        "form": form,
                        "date": date_str,
                        "accepted_at": accepted_at,
                        "accession_number": accession_number,
                        "cik": cik,
                        "link": filing_link,
                        **effectiveness,
                        "_source": "series",
                    }
                )
            for entry in mapped_prospectus_entries:
                rows_to_append.append(
                    {
                        **entry,
                        "filer": resolved_filer_name,
                        "form": form,
                        "date": date_str,
                        "accepted_at": accepted_at,
                        "accession_number": accession_number,
                        "cik": cik,
                        "link": filing_link,
                        **effectiveness,
                        "_source": "mapped_pair",
                    }
                )
        else:
            if all_named_pairs:
                for pair in all_named_pairs:
                    rows_to_append.append(
                        {
                            "ticker": sanitize_ticker(pair.get("ticker", "")),
                            "ticker_source": "filing" if sanitize_ticker(pair.get("ticker", "")) != "Not Listed" else "not_listed",
                            "etf_name": pair.get("etf_name", "N/A"),
                            "class_name": pair.get("etf_name", "N/A"),
                            "series_id": "",
                            "series_name": "",
                            "class_id": "",
                            "vehicle": UNKNOWN_VEHICLE,
                            "identity_scope": "name",
                            "filer": resolved_filer_name,
                            "form": form,
                            "date": date_str,
                            "accepted_at": accepted_at,
                            "accession_number": accession_number,
                            "cik": cik,
                            "link": filing_link,
                            **effectiveness,
                            "_source": "named_pair",
                        }
                    )
            else:
                fallback_name = primary_etf_name if primary_etf_name != "N/A" else extract_etf_name(index_text)
                fallback_ticker = primary_ticker or extract_ticker(index_text) or "Not Listed"
                rows_to_append.append(
                    {
                        "ticker": sanitize_ticker(fallback_ticker),
                        "ticker_source": "filing" if sanitize_ticker(fallback_ticker) != "Not Listed" else "not_listed",
                        "etf_name": fallback_name,
                        "class_name": fallback_name,
                        "series_id": "",
                        "series_name": "",
                        "class_id": "",
                        "vehicle": UNKNOWN_VEHICLE,
                        "identity_scope": "name",
                        "filer": resolved_filer_name,
                        "form": form,
                        "date": date_str,
                        "accepted_at": accepted_at,
                        "accession_number": accession_number,
                        "cik": cik,
                        "link": filing_link,
                        **effectiveness,
                        "_source": "fallback",
                    }
                )

        for row in rows_to_append:
            source = row.pop("_source", "")
            row_name = str(row["etf_name"] or "").strip()
            if not row_name or row_name.upper() == "N/A":
                continue
            class_name = str(row.get("class_name", "") or "").strip()
            if is_share_class_name(class_name) and not row.get("series_id"):
                continue
            if source != "series" and "ETF" not in row_name.upper() and "FUND" not in row_name.upper():
                continue
            row["exchange_listed"] = exchange_listed
            row["vehicle"] = classify_vehicle(row)
            row["identity_scope"] = (
                "series" if uses_parent_series_identity(row) else row["identity_scope"]
            )
            row.pop("exchange_listed", None)
            row.setdefault("ticker_at_filing", row["ticker"])
            identity_token = row.get("class_id") or row.get("series_id") or normalize_etf_name(row_name)
            row["event_id"] = f"{accession_number}:{identity_token}"
            results.append(row)

    return results


def _fetch_filings_for_cik(
    cik: str,
    start_bound: datetime,
    end_bound: datetime,
    primary_document_workers: int = 1,
    ticker_mapping: dict[tuple[str, str, str], str] | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    filer_name = _display_filer_name(cik, CIK_LOOKUP.get(cik, cik))
    try:
        cik_data = fetch_recent_filings_for_cik(cik)
        filer_name = _display_filer_name(
            cik,
            str(cik_data.get("filer_name", CIK_LOOKUP.get(cik, cik))),
        )
        if cik_data.get("_error"):
            raise RuntimeError(str(cik_data["_error"]))
        rows = _fetch_filing_rows_for_cik(
            cik,
            start_bound,
            end_bound,
            cik_data,
            primary_document_workers,
            ticker_mapping,
        )
    except Exception as exc:
        return [], {
            "cik": cik,
            "filer": filer_name,
            "status": "failed",
            "success": False,
            "failed": True,
            "row_count": 0,
            "error_summary": f"{type(exc).__name__}: {exc}",
        }

    return rows, {
        "cik": cik,
        "filer": filer_name,
        "status": "success",
        "success": True,
        "failed": False,
        "row_count": len(rows),
        "error_summary": "",
    }


def finalize_event_rows(
    rows: list[dict[str, str]],
    start_date=None,
    end_date=None,
    ticker_mapping: dict[tuple[str, str, str], str] | None = None,
) -> list[dict[str, str]]:
    start_bound = (
        datetime.combine(start_date, datetime.min.time())
        if start_date
        else datetime.today() - timedelta(days=DAYS_BACK)
    )
    end_bound = (
        datetime.combine(end_date, datetime.max.time())
        if end_date
        else datetime.today()
    )
    mapped_results = _enrich_tickers_from_sec_mapping(
        rows,
        ticker_mapping or {},
    )
    enriched_results = _enrich_missing_tickers_from_later_filings(mapped_results)
    bounded_results = _filter_rows_to_bounds(
        enriched_results,
        start_bound,
        end_bound,
    )
    return sorted(bounded_results, key=_row_timestamp, reverse=True)


def fetch_filing_events(start_date=None, end_date=None, ciks=None) -> FilingEventResults:
    results: list[dict[str, str]] = []
    statuses_by_cik: dict[str, dict[str, Any]] = {}
    start_bound = datetime.combine(start_date, datetime.min.time()) if start_date else datetime.today() - timedelta(days=DAYS_BACK)
    end_bound = datetime.combine(end_date, datetime.max.time()) if end_date else datetime.today()
    enrichment_end_bound = min(datetime.today(), end_bound + timedelta(days=90))
    selected_ciks = list(ciks) if ciks else CIKS
    if not selected_ciks:
        return FilingEventResults()
    ticker_mapping = fetch_sec_fund_ticker_mapping()
    mapping_status = {
        "available": getattr(ticker_mapping, "available", True),
        "error_summary": getattr(ticker_mapping, "error_summary", ""),
    }

    worker_count = max(1, min(SEC_MAX_WORKERS, len(selected_ciks)))
    if worker_count == 1:
        for cik in selected_ciks:
            cik_rows, status = _fetch_filings_for_cik(
                cik,
                start_bound,
                enrichment_end_bound,
                primary_document_workers=4,
                ticker_mapping=ticker_mapping,
            )
            results.extend(cik_rows)
            statuses_by_cik[cik] = status
        return FilingEventResults(
            finalize_event_rows(results, start_date, end_date, ticker_mapping),
            [statuses_by_cik[cik] for cik in selected_ciks],
            mapping_status,
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(
                _fetch_filings_for_cik,
                cik,
                start_bound,
                enrichment_end_bound,
                1,
                ticker_mapping,
            ): cik
            for cik in selected_ciks
        }
        for future in as_completed(future_map):
            cik = future_map[future]
            try:
                cik_rows, status = future.result()
                results.extend(cik_rows)
                statuses_by_cik[cik] = status
            except Exception as exc:
                statuses_by_cik[cik] = {
                    "cik": cik,
                    "filer": _display_filer_name(cik, CIK_LOOKUP.get(cik, cik)),
                    "status": "failed",
                    "success": False,
                    "failed": True,
                    "row_count": 0,
                    "error_summary": f"{type(exc).__name__}: {exc}",
                }

    return FilingEventResults(
        finalize_event_rows(results, start_date, end_date, ticker_mapping),
        [statuses_by_cik[cik] for cik in selected_ciks],
        mapping_status,
    )


def fetch_filings(start_date=None, end_date=None, ciks=None) -> list[dict[str, str]]:
    events = fetch_filing_events(start_date=start_date, end_date=end_date, ciks=ciks)
    return derive_latest_fund_rows(events)
