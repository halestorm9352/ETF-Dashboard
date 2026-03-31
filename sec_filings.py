import time
from datetime import datetime, timedelta

import requests

from config import (
    CIKS,
    CIK_LOOKUP,
    DAYS_BACK,
    FORMS,
    INDEX_PAGE_MAX_CHARS,
    REQUEST_DELAY_SECONDS,
)
from http_utils import get_http_session, get_response_text
from sec_parsers import (
    extract_etf_name,
    extract_ticker,
    sanitize_ticker,
    extract_filer_name,
    extract_series_entries,
    extract_supporting_document_urls,
)


def extract_text(url, max_chars=INDEX_PAGE_MAX_CHARS):
    return get_response_text(url, max_chars)


def fetch_supporting_document_texts(index_text, max_documents=4):
    documents = []
    for url in extract_supporting_document_urls(index_text)[:max_documents]:
        max_chars = 300000
        if url.lower().endswith("_htm.xml"):
            max_chars = 120000

        text = extract_text(url, max_chars=max_chars)
        if text:
            documents.append(text)

    return documents


def fetch_recent_filings_for_cik(cik):
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
            time.sleep(1.0 + attempt)


def fetch_filings(start_date=None, end_date=None):
    results = []
    seen_links = set()
    start_bound = datetime.combine(start_date, datetime.min.time()) if start_date else datetime.today() - timedelta(days=DAYS_BACK)
    end_bound = datetime.combine(end_date, datetime.max.time()) if end_date else datetime.today()

    for cik in CIKS:
        cik_data = fetch_recent_filings_for_cik(cik)
        filer_name = str(cik_data.get("filer_name", CIK_LOOKUP.get(cik, cik))).upper()
        recent = cik_data.get("recent", {})
        if not recent:
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

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
            primary_document = primary_documents[index] if index < len(primary_documents) else ""
            primary_document_url = ""
            if primary_document:
                primary_document_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{accession_clean}/{primary_document}"
                )

            if filing_link in seen_links:
                continue

            seen_links.add(filing_link)
            index_text = extract_text(filing_link, max_chars=INDEX_PAGE_MAX_CHARS)
            filing_filer_name = extract_filer_name(index_text) or filer_name
            series_entries = extract_series_entries(index_text)
            primary_ticker = ""
            primary_etf_name = "N/A"

            if primary_document_url:
                primary_text = extract_text(primary_document_url, max_chars=300000)
                if primary_text:
                    primary_ticker = extract_ticker(primary_text)
                    primary_etf_name = extract_etf_name(primary_text)
                    parsed_filer_name = extract_filer_name(primary_text)
                    if parsed_filer_name:
                        filing_filer_name = parsed_filer_name

            if index_text and ((not series_entries) or any(not entry["ticker"] for entry in series_entries)):
                for supporting_text in fetch_supporting_document_texts(index_text):
                    if not primary_ticker:
                        primary_ticker = extract_ticker(supporting_text)
                    if primary_etf_name == "N/A":
                        primary_etf_name = extract_etf_name(supporting_text)
                    if not filing_filer_name:
                        filing_filer_name = extract_filer_name(supporting_text)
                    if primary_ticker and primary_etf_name != "N/A" and filing_filer_name:
                        break

            resolved_filer_name = filing_filer_name or filer_name
            rows_to_append = []

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

            time.sleep(REQUEST_DELAY_SECONDS)

        time.sleep(REQUEST_DELAY_SECONDS)

    return results
