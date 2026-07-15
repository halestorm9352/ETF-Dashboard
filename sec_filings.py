from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import re
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
    extract_rule_485_effectiveness,
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
    configured_name = CIK_LOOKUP.get(cik, "")
    normalized_name = str(configured_name or filer_name or "").upper()
    if cik in {"0001742912", "0001924868"} or "TIDAL TRUST" in normalized_name:
        return "TIDAL"
    return normalized_name


def _row_timestamp(row: dict[str, str]) -> datetime:
    accepted_at = str(row.get("accepted_at", "")).strip()
    if accepted_at:
        try:
            return datetime.fromisoformat(accepted_at.replace("Z", "+00:00")).replace(tzinfo=None)
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


def _enrich_missing_tickers_from_later_filings(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    latest_ticker_by_fund: dict[tuple[str, str], str] = {}
    enriched_rows = sorted(rows, key=_row_timestamp, reverse=True)

    for row in enriched_rows:
        normalized_name = normalize_etf_name(row.get("etf_name", ""))
        if not normalized_name:
            continue

        key = (row.get("cik", ""), normalized_name)
        ticker = sanitize_ticker(row.get("ticker", ""))
        if ticker != "Not Listed":
            latest_ticker_by_fund.setdefault(key, ticker)
        elif key in latest_ticker_by_fund:
            row["ticker"] = latest_ticker_by_fund[key]

    return rows


def _dedupe_latest_fund_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped_rows: list[dict[str, str]] = []
    seen_funds: set[tuple[str, str]] = set()

    for row in sorted(rows, key=_row_timestamp, reverse=True):
        normalized_name = normalize_etf_name(row.get("etf_name", ""))
        key = (row.get("cik", ""), normalized_name)
        if not normalized_name:
            deduped_rows.append(row)
            continue
        if key in seen_funds:
            continue
        seen_funds.add(key)
        deduped_rows.append(row)

    return deduped_rows


def derive_latest_fund_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    copied_rows = [dict(row) for row in rows]
    history_by_fund: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in sorted(copied_rows, key=_row_timestamp):
        normalized_name = normalize_etf_name(row.get("etf_name", ""))
        if not normalized_name:
            continue
        key = (row.get("cik", ""), normalized_name)
        history_by_fund.setdefault(key, []).append(row)

    latest_rows = _dedupe_latest_fund_rows(copied_rows)
    for row in latest_rows:
        normalized_name = normalize_etf_name(row.get("etf_name", ""))
        history = history_by_fund.get((row.get("cik", ""), normalized_name), [row])
        forms = [str(event.get("form", "") or "").upper() for event in history]
        forms = [form for form in forms if form]
        row["filing_event_count"] = len(history)
        row["amendment_count"] = sum(
            form in {"485APOS", "485BPOS"} for form in forms
        )
        row["filing_form_history"] = " -> ".join(forms)

    return latest_rows


def _is_placeholder_share_class_name(name: str) -> bool:
    return bool(re.fullmatch(r"Class\s+[A-Z0-9]+", str(name or "").strip(), re.IGNORECASE))


def _fetch_filings_for_cik(
    cik: str,
    start_bound: datetime,
    end_bound: datetime,
    primary_document_workers: int = 1,
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
            prefetched_primary_text[url] = extract_text(url, max_chars=300000)
    elif primary_document_urls:
        with ThreadPoolExecutor(max_workers=primary_worker_count) as executor:
            future_map = {
                executor.submit(extract_text, url, 300000): url
                for url in primary_document_urls
            }
            for future in as_completed(future_map):
                url = future_map[future]
                try:
                    prefetched_primary_text[url] = future.result()
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
        primary_text = ""
        primary_ticker = ""
        primary_etf_name = "N/A"
        primary_named_pairs: list[dict[str, str]] = []

        needs_primary_text = _needs_primary_document(series_entries, filing_filer_name)
        needs_effectiveness_context = form in {"485APOS", "485BPOS"}
        if primary_document_url and (needs_primary_text or needs_effectiveness_context):
            if primary_document_url in prefetched_primary_text:
                primary_text = prefetched_primary_text[primary_document_url]
            else:
                primary_text = extract_text(primary_document_url, max_chars=300000)
            if primary_text and needs_primary_text:
                primary_named_pairs = extract_named_ticker_pairs(primary_text)
                primary_ticker = extract_ticker(
                    primary_text,
                    named_ticker_pairs=primary_named_pairs,
                )
                primary_etf_name = extract_etf_name(primary_text)
                if not filing_filer_name:
                    filing_filer_name = extract_filer_name(primary_text)

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
                        "accepted_at": accepted_at,
                        "accession_number": accession_number,
                        "cik": cik,
                        "link": filing_link,
                        **effectiveness,
                        "_source": "series",
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
                        "etf_name": fallback_name,
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
            if _is_placeholder_share_class_name(row_name):
                continue
            if source != "series" and "ETF" not in row_name.upper() and "FUND" not in row_name.upper():
                continue
            row["ticker_at_filing"] = row["ticker"]
            row["event_id"] = f"{accession_number}:{normalize_etf_name(row_name)}"
            results.append(row)

    return results


def fetch_filing_events(start_date=None, end_date=None, ciks=None) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    start_bound = datetime.combine(start_date, datetime.min.time()) if start_date else datetime.today() - timedelta(days=DAYS_BACK)
    end_bound = datetime.combine(end_date, datetime.max.time()) if end_date else datetime.today()
    enrichment_end_bound = max(end_bound, datetime.today())
    selected_ciks = list(ciks) if ciks else CIKS
    if not selected_ciks:
        return results

    worker_count = max(1, min(SEC_MAX_WORKERS, len(selected_ciks)))
    if worker_count == 1:
        for cik in selected_ciks:
            results.extend(
                _fetch_filings_for_cik(
                    cik,
                    start_bound,
                    enrichment_end_bound,
                    primary_document_workers=4,
                )
            )
        enriched_results = _enrich_missing_tickers_from_later_filings(results)
        bounded_results = _filter_rows_to_bounds(enriched_results, start_bound, end_bound)
        return sorted(bounded_results, key=_row_timestamp, reverse=True)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(
                _fetch_filings_for_cik,
                cik,
                start_bound,
                enrichment_end_bound,
                1,
            ): cik
            for cik in selected_ciks
        }
        for future in as_completed(future_map):
            try:
                results.extend(future.result())
            except Exception:
                continue

    enriched_results = _enrich_missing_tickers_from_later_filings(results)
    bounded_results = _filter_rows_to_bounds(enriched_results, start_bound, end_bound)
    return sorted(bounded_results, key=_row_timestamp, reverse=True)


def fetch_filings(start_date=None, end_date=None, ciks=None) -> list[dict[str, str]]:
    events = fetch_filing_events(start_date=start_date, end_date=end_date, ciks=ciks)
    return derive_latest_fund_rows(events)
