from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import requests

from config import (
    CIKS,
    CIK_LOOKUP,
    DAYS_BACK,
    FORMS,
    INDEX_PAGE_MAX_CHARS,
    MAX_SUPPORTING_DOCUMENTS,
    SEC_MAX_WORKERS,
)
from http_utils import get_http_session, get_response_text
from sec_parsers import (
    extract_etf_name,
    extract_filer_name,
    extract_named_ticker_pairs,
    extract_series_entries,
    extract_supporting_document_urls,
    extract_ticker,
    normalize_etf_name,
    sanitize_ticker,
)


def extract_text(url: str, max_chars: int = INDEX_PAGE_MAX_CHARS) -> str:
    return get_response_text(url, max_chars)


def fetch_supporting_document_texts(
    index_text: str,
    max_documents: int = MAX_SUPPORTING_DOCUMENTS,
) -> list[str]:
    documents: list[str] = []
    for url in extract_supporting_document_urls(index_text)[:max_documents]:
        max_chars = 300000
        if url.lower().endswith("_htm.xml"):
            max_chars = 120000

        text = extract_text(url, max_chars=max_chars)
        if text:
            documents.append(text)

    return documents


def fetch_recent_filings_for_cik(cik: str) -> dict[str, Any]:
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    session = get_http_session()
    for attempt in range(3):
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
            data = response.json()
            return {
                "filer_name": data.get("name", CIK_LOOKUP.get(cik, cik)),
                "recent": data.get("filings", {}).get("recent", {}),
            }
        except requests.RequestException:
            if attempt == 2:
                return {
                    "filer_name": CIK_LOOKUP.get(cik, cik),
                    "recent": {},
                }

    return {
        "filer_name": CIK_LOOKUP.get(cik, cik),
        "recent": {},
    }


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
        ticker = pair.get("ticker", "")
        if normalized_name and ticker:
            pair_lookup[normalized_name] = ticker

    for entry in merged_entries:
        if entry.get("ticker"):
            continue
        normalized_entry_name = normalize_etf_name(entry.get("etf_name", ""))
        if normalized_entry_name in pair_lookup:
            entry["ticker"] = pair_lookup[normalized_entry_name]
            continue
        for pair_name, pair_ticker in pair_lookup.items():
            if normalized_entry_name and (
                normalized_entry_name in pair_name or pair_name in normalized_entry_name
            ):
                entry["ticker"] = pair_ticker
                break

    return merged_entries


def _display_filer_name(cik: str, filer_name: str) -> str:
    normalized_name = str(filer_name or "").upper()
    if cik in {"0001742912", "0001924868"} or "TIDAL TRUST" in normalized_name:
        return "TIDAL"
    return normalized_name


def _fetch_filings_for_cik(
    cik: str,
    start_bound: datetime,
    end_bound: datetime,
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen_links: set[str] = set()
    cik_data = fetch_recent_filings_for_cik(cik)
    filer_name = str(cik_data.get("filer_name", CIK_LOOKUP.get(cik, cik))).upper()
    recent = cik_data.get("recent", {})
    if not recent:
        return results

    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    accession_numbers = recent.get("accessionNumber", [])
    primary_documents = recent.get("primaryDocument", [])

    for index, form in enumerate(forms):
        if form not in FORMS:
            continue
        if index >= len(filing_dates) or index >= len(accession_numbers):
            continue

        date_str = filing_dates[index]
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
        primary_ticker = ""
        primary_etf_name = "N/A"
        primary_named_pairs: list[dict[str, str]] = []

        if primary_document_url and _needs_primary_document(series_entries, filing_filer_name):
            primary_text = extract_text(primary_document_url, max_chars=300000)
            if primary_text:
                primary_ticker = extract_ticker(primary_text)
                primary_etf_name = extract_etf_name(primary_text)
                primary_named_pairs = extract_named_ticker_pairs(primary_text)
                parsed_filer_name = extract_filer_name(primary_text)
                if parsed_filer_name:
                    filing_filer_name = parsed_filer_name

        supporting_named_pairs: list[dict[str, str]] = []
        if index_text and _needs_supporting_documents(
            series_entries,
            primary_ticker,
            primary_etf_name,
            filing_filer_name,
        ):
            for supporting_text in fetch_supporting_document_texts(index_text):
                if not primary_ticker:
                    primary_ticker = extract_ticker(supporting_text)
                if primary_etf_name == "N/A":
                    primary_etf_name = extract_etf_name(supporting_text)
                supporting_named_pairs.extend(extract_named_ticker_pairs(supporting_text))
                if not filing_filer_name:
                    filing_filer_name = extract_filer_name(supporting_text)
                if primary_ticker and primary_etf_name != "N/A" and filing_filer_name:
                    break

        all_named_pairs = primary_named_pairs + supporting_named_pairs
        if series_entries:
            series_entries = _merge_series_entries_with_pairs(series_entries, all_named_pairs)

        resolved_filer_name = _display_filer_name(cik, filing_filer_name or filer_name)
        rows_to_append: list[dict[str, str]] = []

        if series_entries:
            for entry in series_entries:
                row_name = entry["etf_name"] or primary_etf_name
                row_ticker = entry["ticker"]
                if len(series_entries) == 1 and not row_ticker:
                    row_ticker = primary_ticker
                rows_to_append.append(
                    {
                        "ticker": sanitize_ticker(row_ticker),
                        "etf_name": row_name,
                        "filer": resolved_filer_name,
                        "form": form,
                        "date": date_str,
                        "link": filing_link,
                    }
                )
        else:
            if all_named_pairs:
                for pair in all_named_pairs:
                    rows_to_append.append(
                        {
                            "ticker": sanitize_ticker(pair.get("ticker", "")),
                            "etf_name": pair.get("etf_name", "N/A"),
                            "filer": resolved_filer_name,
                            "form": form,
                            "date": date_str,
                            "link": filing_link,
                        }
                    )
            else:
                fallback_name = primary_etf_name if primary_etf_name != "N/A" else extract_etf_name(index_text)
                fallback_ticker = primary_ticker or extract_ticker(index_text) or "Not Listed"
                rows_to_append.append(
                    {
                        "ticker": sanitize_ticker(fallback_ticker),
                        "etf_name": fallback_name,
                        "filer": resolved_filer_name,
                        "form": form,
                        "date": date_str,
                        "link": filing_link,
                    }
                )

        for row in rows_to_append:
            if "ETF" not in str(row["etf_name"]).upper():
                continue
            results.append(row)

    return results


def fetch_filings(start_date=None, end_date=None, ciks=None) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    start_bound = datetime.combine(start_date, datetime.min.time()) if start_date else datetime.today() - timedelta(days=DAYS_BACK)
    end_bound = datetime.combine(end_date, datetime.max.time()) if end_date else datetime.today()
    selected_ciks = list(ciks) if ciks else CIKS
    if not selected_ciks:
        return results

    worker_count = max(1, min(SEC_MAX_WORKERS, len(selected_ciks)))
    if worker_count == 1:
        for cik in selected_ciks:
            results.extend(_fetch_filings_for_cik(cik, start_bound, end_bound))
        return results

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(_fetch_filings_for_cik, cik, start_bound, end_bound): cik
            for cik in selected_ciks
        }
        for future in as_completed(future_map):
            try:
                results.extend(future.result())
            except Exception:
                continue

    return results
